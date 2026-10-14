import pytest

from quetzal_ingestion import __main__ as cli


def test_the_job_name_selects_what_runs(monkeypatch):
    calls = []
    monkeypatch.setitem(cli.JOBS, "exchange-rates", calls.append)

    cli.main(["exchange-rates", "--from-year", "2025"])

    assert calls == [["--from-year", "2025"]]


@pytest.mark.parametrize("argv", [[], ["unknown-job"]])
def test_a_missing_or_unknown_job_name_shows_the_available_jobs(argv):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv)

    assert "exchange-rates" in str(exit_info.value)
