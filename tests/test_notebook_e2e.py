'''
Copyright 2018-2026 AVEVA Group Limited

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
SPDX-License-Identifier: Apache-2.0

These end-to-end tests execute the notebook workflow with mocked REST and
filesystem dependencies to verify metadata discovery and data-loading logic
without calling external services.
'''

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


NOTEBOOK_PATH = Path(__file__).resolve().parents[1] / "CONNECT_Iceberg_REST_Time_Series_Data.ipynb"


class _NamedBytesIO(io.BytesIO):
    def __init__(self, path: str):
        super().__init__(b"mock")
        self.name = path


class _FakeFS:
    def open(self, path: str, mode: str = "rb"):
        return _NamedBytesIO(path)


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def notebook_code_cells() -> list[str]:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    return ["\n".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"]


def test_notebook_end_to_end_with_mocked_iceberg_rest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, notebook_code_cells: list[str]):
    appsettings = {
        "qualifiedName": "mock-warehouse",
        "bearerToken": "mock-token",
        "icebergEndpoint": "https://mock-iceberg.example/api/2.0/iceberg",
    }
    (tmp_path / "appsettings.json").write_text(json.dumps(appsettings), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    rest_calls = []

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        rest_calls.append(
            {
                "url": url,
                "headers": headers,
                "params": params,
                "verify": verify,
                "timeout": timeout,
            }
        )

        if url.endswith("/v1/config"):
            return _FakeResponse(
                {
                    "overrides": {"prefix": "demo_prefix"},
                    "endpoints": ["/v1/{prefix}/namespaces", "/v1/{prefix}/namespaces/{namespace}/tables"],
                }
            )
        if url.endswith("/v1/demo_prefix/namespaces"):
            return _FakeResponse({"namespaces": [["demo_ns"]]})
        if url.endswith("/v1/demo_prefix/namespaces/demo_ns/tables"):
            return _FakeResponse({"identifiers": [{"name": "demo_table"}]})
        if url.endswith("/v1/demo_prefix/namespaces/demo_ns/tables/demo_table"):
            return _FakeResponse(
                {
                    "metadata": {
                        "snapshots": [
                            {
                                "manifest-list": "abfs://container/manifest-list.avro",
                                "summary": {"total-records": "3"},
                            }
                        ],
                        "schemas": [
                            {
                                "fields": [
                                    {"name": "EventTime"},
                                    {"name": "Field"},
                                    {"name": "Value"},
                                ]
                            }
                        ],
                    },
                    "config": {
                        "adls.sas-token.mockaccount.core.windows.net": "sv=mock-sas-token",
                    },
                }
            )

        raise AssertionError(f"Unexpected REST URL: {url}")

    def fake_reader(file_obj):
        path = getattr(file_obj, "name", "")
        if path.endswith("manifest-list.avro"):
            return [{"manifest_path": "abfs://container/manifest-1.avro"}]
        if path.endswith("manifest-1.avro"):
            return [{"data_file": {"file_path": "abfs://container/data-1.parquet"}}]
        raise AssertionError(f"Unexpected file for fastavro.reader: {path}")

    def fake_read_parquet(path, filesystem=None):
        assert path == "abfs://container/data-1.parquet"
        assert isinstance(filesystem, _FakeFS)
        return pd.DataFrame(
            {
                "c1": pd.to_datetime([
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T01:00:00Z",
                    "2026-01-01T02:00:00Z",
                ]),
                "c2": ["Temperature", "Pressure", "Temperature"],
                "c3": [20.1, 2.3, 20.4],
            }
        )

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("fsspec.filesystem", lambda *args, **kwargs: _FakeFS())
    monkeypatch.setattr("fastavro.reader", fake_reader)
    monkeypatch.setattr("pandas.read_parquet", fake_read_parquet)
    monkeypatch.setattr("plotly.graph_objs._figure.Figure.show", lambda self: None)

    notebook_globals = {}
    for source in notebook_code_cells:
        exec(source, notebook_globals)

    expected_urls = [
        "https://mock-iceberg.example/api/2.0/iceberg/v1/config",
        "https://mock-iceberg.example/api/2.0/iceberg/v1/demo_prefix/namespaces",
        "https://mock-iceberg.example/api/2.0/iceberg/v1/demo_prefix/namespaces/demo_ns/tables",
        "https://mock-iceberg.example/api/2.0/iceberg/v1/demo_prefix/namespaces/demo_ns/tables/demo_table",
    ]
    assert [call["url"] for call in rest_calls] == expected_urls

    for call in rest_calls:
        assert call["headers"] == {"Authorization": "Bearer mock-token"}
        assert call["verify"] is False
        assert call["timeout"] == 60

    assert rest_calls[0]["params"] == {"warehouse": "mock-warehouse"}
    assert rest_calls[1]["params"] is None
    assert rest_calls[2]["params"] is None
    assert rest_calls[3]["params"] is None

    assert notebook_globals["table_name"] == "demo_table"
    assert notebook_globals["namespace"] == "demo_ns"
    assert notebook_globals["all_data_file_paths"] == ["abfs://container/data-1.parquet"]
    assert notebook_globals["column_names"] == ["EventTime", "Field", "Value"]
    assert notebook_globals["df"].shape == (3, 3)
    assert notebook_globals["timestamp_col"] == "EventTime"
    assert notebook_globals["chart_title"] == "Narrow Table: Field Values vs EventTime"


def test_notebook_plotting_wide_mode_reuses_prepared_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    notebook_code_cells: list[str],
):
    # Re-run full flow first, then re-execute plotting cell in wide mode to validate both code paths.
    appsettings = {
        "qualifiedName": "mock-warehouse",
        "bearerToken": "mock-token",
        "icebergEndpoint": "https://mock-iceberg.example/api/2.0/iceberg",
    }
    (tmp_path / "appsettings.json").write_text(json.dumps(appsettings), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url.endswith("/v1/config"):
            return _FakeResponse({"overrides": {"prefix": "demo_prefix"}, "endpoints": []})
        if url.endswith("/v1/demo_prefix/namespaces"):
            return _FakeResponse({"namespaces": [["demo_ns"]]})
        if url.endswith("/v1/demo_prefix/namespaces/demo_ns/tables"):
            return _FakeResponse({"identifiers": [{"name": "demo_table"}]})
        if url.endswith("/v1/demo_prefix/namespaces/demo_ns/tables/demo_table"):
            return _FakeResponse(
                {
                    "metadata": {
                        "snapshots": [
                            {
                                "manifest-list": "abfs://container/manifest-list.avro",
                                "summary": {"total-records": "2"},
                            }
                        ],
                        "schemas": [
                            {
                                "fields": [
                                    {"name": "EventTime"},
                                    {"name": "Field"},
                                    {"name": "Value"},
                                ]
                            }
                        ],
                    },
                    "config": {
                        "adls.sas-token.mockaccount.core.windows.net": "sv=mock-sas-token",
                    },
                }
            )
        raise AssertionError(f"Unexpected REST URL: {url}")

    def fake_reader(file_obj):
        path = getattr(file_obj, "name", "")
        if path.endswith("manifest-list.avro"):
            return [{"manifest_path": "abfs://container/manifest-1.avro"}]
        if path.endswith("manifest-1.avro"):
            return [{"data_file": {"file_path": "abfs://container/data-1.parquet"}}]
        raise AssertionError(f"Unexpected file for fastavro.reader: {path}")

    def fake_read_parquet(path, filesystem=None):
        return pd.DataFrame(
            {
                "c1": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"]),
                "c2": ["Temperature", "Pressure"],
                "c3": [20.1, 2.3],
            }
        )

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("fsspec.filesystem", lambda *args, **kwargs: _FakeFS())
    monkeypatch.setattr("fastavro.reader", fake_reader)
    monkeypatch.setattr("pandas.read_parquet", fake_read_parquet)
    monkeypatch.setattr("plotly.graph_objs._figure.Figure.show", lambda self: None)

    notebook_globals = {}
    for source in notebook_code_cells:
        exec(source, notebook_globals)

    notebook_globals["table_mode"] = "wide"
    exec(notebook_code_cells[-1], notebook_globals)

    assert notebook_globals["chart_title"] == "Metrics and Dimensions vs EventTime"
