"""AWS pieces tested WITHOUT an AWS account: S3 execution adapter and SNS alert channel against botocore's Stubber
(no network), and static checks of the eu-north-1 deployment templates (least privilege, encryption, no SSH)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
AWS = ROOT / "deploy" / "aws"


# ----------------------------------------------------------------------------- CloudFormation YAML with short tags
class CfnLoader(yaml.SafeLoader):
    pass


def _tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        v = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        v = loader.construct_sequence(node, deep=True)
    else:
        v = loader.construct_mapping(node, deep=True)
    return {f"Fn::{suffix}" if suffix not in ("Ref",) else "Ref": v}


CfnLoader.add_multi_constructor("!", _tag)


def load(name):
    return yaml.load((AWS / name).read_text(), Loader=CfnLoader)


def statements():
    return load("bootstrap.yaml")["Resources"]["DeployerPolicy"]["Properties"]["PolicyDocument"]["Statement"]


def _actions(st):
    a = st["Action"]
    return [a] if isinstance(a, str) else a


def test_deployer_policy_has_no_wildcard_service_or_iam_write():
    for st in statements():
        assert st["Effect"] == "Allow"
        for a in _actions(st):
            assert a != "*" and not a.endswith(":*"), a
            assert not re.match(r"iam:(Create|Delete|Attach|Detach|Put|Update|Add|Remove)", a), f"IAM write {a}"
    passrole = [s for s in statements() if "iam:PassRole" in _actions(s)]
    assert len(passrole) == 1 and passrole[0]["Condition"]["StringEquals"]["iam:PassedToService"] == "ec2.amazonaws.com"


def test_deployer_ec2_rights_limited_to_stockholm_and_resources_scoped():
    ec2 = [s for s in statements() if any(a.startswith("ec2:") for a in _actions(s))]
    assert ec2 and all(s["Condition"]["StringEquals"]["aws:RequestedRegion"] == "eu-north-1" for s in ec2)
    for s in statements():
        if s["Sid"] in ("AppBucketOnly", "AlertTopicOnly", "LogsOnlyHcf", "AppParametersOnly", "AlarmsOnlyHcf"):
            assert "*" != s["Resource"], s["Sid"]


def test_deployer_policy_fits_iam_size_limit():
    # IAM managed policies may hold 6,144 characters excluding whitespace; account id ~12 chars per ARN
    doc = json.dumps({"Version": "2012-10-17", "Statement": statements()}, separators=(",", ":"))
    assert len(re.sub(r"\s", "", doc)) < 6144


def test_instance_role_reads_only_its_own_secrets_and_bucket():
    pol = load("bootstrap.yaml")["Resources"]["InstanceRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    text = json.dumps(pol)
    assert "parameter/hcf/prod/*" in text and "hcf-app-" in text
    assert '"Resource": "*"' not in text


def test_app_stack_no_ssh_imdsv2_encrypted_disk_single_ip():
    res = load("app.yaml")["Resources"]
    ingress = res["WebSecurityGroup"]["Properties"]["SecurityGroupIngress"]
    assert len(ingress) == 1 and ingress[0]["FromPort"] == 80 and ingress[0]["CidrIp"] == {"Ref": "AllowedCidr"}
    inst = res["AppServer"]["Properties"]
    assert inst["MetadataOptions"]["HttpTokens"] == "required"
    assert inst["BlockDeviceMappings"][0]["Ebs"]["Encrypted"] is True
    assert "KeyName" not in inst  # no SSH key pair; access via SSM Session Manager
    params = load("app.yaml")["Parameters"]
    assert params["InstanceType"]["AllowedValues"] == ["t3.micro", "t3.small"]
    assert re.match(params["AllowedCidr"]["AllowedPattern"], "203.0.113.7/32")


def test_release_bundle_excludes_raw_data_and_secrets():
    s = (AWS / "scripts" / "03_upload_release.sh").read_text()
    tar_line = next(line for line in s.splitlines() if line.startswith("tar --exclude"))
    assert "dataset/raw" not in tar_line and ".env" not in tar_line
    assert "dataset/raw|\\.env$" in s  # explicit guard after packaging


def test_no_secret_values_in_deploy_files():
    for p in AWS.rglob("*"):
        if p.is_file():
            t = p.read_text(errors="ignore")
            assert not re.search(r"AKIA[0-9A-Z]{16}", t), p
            assert not re.search(r"(SECRET_KEY|PASSWORD)=[A-Za-z0-9_\-]{12,}", t), p


# ----------------------------------------------------------------------------- adapters against botocore Stubber
boto3 = pytest.importorskip("boto3")
from botocore.stub import ANY, Stubber  # noqa: E402


@pytest.fixture
def region(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")


def test_s3_adapter_puts_encrypted_object(region):
    from src.execution.adapters import S3CloudAdapter

    a = S3CloudAdapter("hcf-app-000000000000-eu-north-1")
    payload = {"event_id": "ev-1", "device_id": "ICU-1", "criticality": 2.0, "decision": {"destination": "CLOUD"}}
    with Stubber(a.s3) as stub:
        stub.add_response("put_object", {"ETag": '"abc"'},
                          {"Bucket": "hcf-app-000000000000-eu-north-1", "Key": ANY,
                           "ServerSideEncryption": "AES256", "Body": ANY})
        out = a.execute(payload)
        stub.assert_no_pending_responses()
    assert out.output_ref.startswith("s3://hcf-app-000000000000-eu-north-1/processed/") and out.output_ref.endswith("/ICU-1/ev-1.json")


def test_s3_adapter_error_becomes_execution_error(region):
    from src.execution.adapters import ExecutionError, S3CloudAdapter

    a = S3CloudAdapter("b")
    with Stubber(a.s3) as stub:
        stub.add_client_error("put_object", service_error_code="AccessDenied", http_status_code=403)
        with pytest.raises(ExecutionError, match="S3 put_object failed"):
            a.execute({"event_id": "ev-2", "device_id": "ICU-1", "criticality": 1.0})


def test_sns_channel_publishes(region, monkeypatch):
    import botocore.session

    from backend.services.alerts import SNSChannel

    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:eu-north-1:000000000000:hcf-alerts")
    client = botocore.session.get_session().create_client("sns", region_name="eu-north-1")
    monkeypatch.setattr(boto3, "client", lambda *a, **k: client)
    ch = SNSChannel(SimpleNamespace())
    assert ch.configured()
    alert = SimpleNamespace(severity="CRITICAL", kind="emergency_override", message="EMERGENCY: device X")
    with Stubber(client) as stub:
        stub.add_response("publish", {"MessageId": "m-1"},
                          {"TopicArn": "arn:aws:sns:eu-north-1:000000000000:hcf-alerts", "Subject": ANY, "Message": "EMERGENCY: device X"})
        assert ch.send(alert) == "sns MessageId=m-1"
