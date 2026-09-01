from airdropd.localsend import (
    Announce,
    DeviceInfo,
    FileRequest,
    PrepareUploadRequest,
    build_prepare_upload_request,
    build_prepare_upload_response,
)


def test_announce_payload_shape():
    a = Announce(alias="box", fingerprint="fp123", port=53317, protocol="https")
    data = a.to_json()
    assert data == {
        "alias": "box",
        "deviceModel": "linux",
        "deviceType": "desktop",
        "fingerprint": "fp123",
        "port": 53317,
        "protocol": "https",
        "download": False,
    }
    assert Announce.from_json(data) == a


def test_announce_from_json_rejects_garbage():
    assert Announce.from_json({"alias": "x"}) is None
    assert Announce.from_json({"alias": 1, "fingerprint": [], "port": "x", "protocol": 2}) is None
    assert Announce.from_json("nope") is None


def test_prepare_request_roundtrip():
    sender = DeviceInfo(alias="sender", fingerprint="abc")
    files = [FileRequest(file_id="0", file_name="a.txt", size=10),
             FileRequest(file_id="1", file_name="b.bin", size=99, file_type="application/octet-stream")]
    payload = build_prepare_upload_request(sender, files)
    parsed = PrepareUploadRequest.from_json(payload)
    assert parsed is not None
    assert parsed.sender.alias == "sender"
    assert [f.file_name for f in parsed.files] == ["a.txt", "b.bin"]
    assert parsed.files[1].size == 99


def test_prepare_response_shape():
    resp = build_prepare_upload_response("sess1", {"0": "tok"})
    assert resp == {"sessionId": "sess1", "files": {"0": "tok"}}
