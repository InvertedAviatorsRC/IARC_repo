from property_lookup.cli import main


def test_cli_works_in_mock_mode(capsys):
    exit_code = main(["123 Main St, Philadelphia, PA", "--mock"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "## Property Lookup Result" in captured.out
    assert "Estimated Value: $325,000" in captured.out
    assert captured.err == ""


def test_cli_without_key_reports_helpful_error(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROPERTY_PROVIDER", "rentcast")
    monkeypatch.delenv("RENTCAST_API_KEY", raising=False)

    exit_code = main(["123 Main St, Philadelphia, PA"])

    assert exit_code == 2
    assert "RENTCAST_API_KEY" in capsys.readouterr().err
