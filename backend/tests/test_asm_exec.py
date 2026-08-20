import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch


def _load_asm_exec():
    path = Path(__file__).resolve().parents[1] / "asm-exec"
    loader = SourceFileLoader("asm_exec", str(path))
    spec = importlib.util.spec_from_loader("asm_exec", loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_get_aws_credentials_uses_ecs_relative_uri_without_exposing_values():
    asm_exec = _load_asm_exec()
    payload = {
        "AccessKeyId": "temporary-access-key",
        "SecretAccessKey": "temporary-secret-key",
        "Token": "temporary-session-token",
    }

    with patch.dict(
        asm_exec.os.environ,
        {"AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/v2/credentials/task"},
        clear=True,
    ), patch.object(
        asm_exec.urllib.request,
        "urlopen",
        return_value=_Response(payload),
    ) as urlopen:
        credentials = asm_exec._get_aws_credentials()

    assert credentials == {
        "access_key": payload["AccessKeyId"],
        "secret_key": payload["SecretAccessKey"],
        "token": payload["Token"],
    }
    assert urlopen.call_args.args[0].full_url == (
        "http://169.254.170.2/v2/credentials/task"
    )
