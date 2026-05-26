"""Test cron expression ↔ cron-job.org dict converter."""

import pytest

from cron_job_org_mcp.schedule import cron_to_dict, dict_to_cron


class TestCronToDict:
    def test_every_2_minutes(self):
        d = cron_to_dict("*/2 * * * *")
        assert d["minutes"] == list(range(0, 60, 2))
        assert d["hours"] == [-1]
        assert d["mdays"] == [-1]
        assert d["months"] == [-1]
        assert d["wdays"] == [-1]
        assert d["timezone"] == "Europe/Warsaw"

    def test_monday_8am(self):
        d = cron_to_dict("0 8 * * 1")
        assert d["minutes"] == [0]
        assert d["hours"] == [8]
        assert d["wdays"] == [1]
        assert d["mdays"] == [-1]
        assert d["months"] == [-1]

    def test_daily_730(self):
        d = cron_to_dict("30 7 * * *")
        assert d["minutes"] == [30]
        assert d["hours"] == [7]
        assert d["wdays"] == [-1]

    def test_every_10_minutes(self):
        d = cron_to_dict("*/10 * * * *")
        assert d["minutes"] == [0, 10, 20, 30, 40, 50]

    def test_list_values(self):
        d = cron_to_dict("0,15,30,45 * * * *")
        assert d["minutes"] == [0, 15, 30, 45]

    def test_range(self):
        d = cron_to_dict("0 9-17 * * 1-5")
        assert d["hours"] == [9, 10, 11, 12, 13, 14, 15, 16, 17]
        assert d["wdays"] == [1, 2, 3, 4, 5]

    def test_custom_timezone(self):
        d = cron_to_dict("0 12 * * *", timezone="UTC")
        assert d["timezone"] == "UTC"

    def test_invalid_field_count(self):
        with pytest.raises(ValueError):
            cron_to_dict("* * * *")
        with pytest.raises(ValueError):
            cron_to_dict("0 7 * * * *")


class TestDictToCron:
    def test_every_2_minutes(self):
        d = {"minutes": list(range(0, 60, 2)), "hours": [-1], "mdays": [-1], "months": [-1], "wdays": [-1]}
        assert dict_to_cron(d) == "*/2 * * * *"

    def test_monday_8am(self):
        d = {"minutes": [0], "hours": [8], "mdays": [-1], "months": [-1], "wdays": [1]}
        assert dict_to_cron(d) == "0 8 * * 1"

    def test_full_wildcard(self):
        d = {"minutes": [-1], "hours": [-1], "mdays": [-1], "months": [-1], "wdays": [-1]}
        assert dict_to_cron(d) == "* * * * *"

    def test_range_compaction(self):
        d = {"minutes": [0], "hours": [9, 10, 11, 12, 13], "mdays": [-1], "months": [-1], "wdays": [-1]}
        assert dict_to_cron(d) == "0 9-13 * * *"

    def test_list_compaction(self):
        # [0,15,30,45] matches */15 step pattern — equivalent to comma list, but compacter
        d = {"minutes": [0, 15, 30, 45], "hours": [-1], "mdays": [-1], "months": [-1], "wdays": [-1]}
        assert dict_to_cron(d) == "*/15 * * * *"

    def test_irregular_list_uses_commas(self):
        # Non-step pattern falls back to comma list
        d = {"minutes": [0, 7, 23, 41], "hours": [-1], "mdays": [-1], "months": [-1], "wdays": [-1]}
        assert dict_to_cron(d) == "0,7,23,41 * * * *"

    def test_empty_schedule(self):
        assert dict_to_cron({}) == "?"

    def test_roundtrip_every_2_min(self):
        original = "*/2 * * * *"
        d = cron_to_dict(original)
        back = dict_to_cron(d)
        assert back == original

    def test_roundtrip_monday_8(self):
        original = "0 8 * * 1"
        d = cron_to_dict(original)
        back = dict_to_cron(d)
        assert back == original
