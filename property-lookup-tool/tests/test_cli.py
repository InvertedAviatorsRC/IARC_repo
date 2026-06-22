from property_lookup.cli import main


def test_cli_works_in_mock_mode(capsys):
    exit_code = main(["123 Main St, Philadelphia, PA", "--mock"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Property Lookup Result" in captured.out
    assert "Estimated Market Value: $325,000" in captured.out
    assert captured.err == ""


def test_cli_without_key_reports_helpful_error(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROPERTY_PROVIDER", "rentcast")
    monkeypatch.delenv("RENTCAST_API_KEY", raising=False)

    exit_code = main(["123 Main St, Philadelphia, PA"])

    assert exit_code == 2
    assert "RENTCAST_API_KEY" in capsys.readouterr().err


def test_cli_does_not_crash_when_public_fields_are_unavailable(monkeypatch, capsys):
    from property_lookup.models import PropertyData

    class PartialService:
        def lookup(self, address):
            return PropertyData(
                input_address=address,
                normalized_address=address,
                state="MN",
                county="Koochiching County",
                source="Minnesota public lookup",
                source_url="https://example.gov/public",
                raw_data={"coverage_message": "County provider is not implemented yet."},
            ).refresh_unavailable_fields()

    monkeypatch.setattr(
        "property_lookup.cli.build_property_service", lambda settings, force_mock: PartialService()
    )
    exit_code = main(["100 Main St, International Falls, MN 56649"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Not available from free public source" in captured.out
    assert "Coverage Note: County provider is not implemented yet." in captured.out
    assert captured.err == ""
