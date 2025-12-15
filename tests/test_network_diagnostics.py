import os


def test_network_diagnostics_log(tmp_path):
    from network_diagnostics import DroneNetworkDiagnostics

    dn = DroneNetworkDiagnostics()
    # override log file to tmp path
    dn.log_file = str(tmp_path / "dn_test.log")
    dn.log("Test entry")
    assert os.path.exists(dn.log_file)
    with open(dn.log_file, "r") as f:
        contents = f.read()
    assert "Test entry" in contents
