"""Recreate the data/raw/ context tables from the Tableau workbook extracts.

Optional: needs `pip install tableauhyperapi`.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import pandas as pd
from tableauhyperapi import Connection, CreateMode, HyperProcess, Telemetry

ROOT = Path(__file__).resolve().parents[1]
TWBX = ROOT / "tableau" / "Data_Viz_Project_2.twbx"
RAW = ROOT / "data" / "raw"

TARGETS = {
    "ds205_dati_quartieri": "population_by_nil_2011_2023.csv",
    "Immobiliare!by!NIL": "immobiliare_prices_by_nil.csv",
    "Driving Distances": "driving_distances_by_nil.csv",
}
ROUTES_FILE = "federated.hyper"


def read_table(conn: Connection, table) -> pd.DataFrame:
    cols = [c.name.unescaped for c in conn.catalog.get_table_definition(table).columns]
    query = "SELECT " + ", ".join('"' + c.replace('"', '""') + '"' for c in cols) + f" FROM {table}"
    return pd.DataFrame(conn.execute_list_query(query), columns=cols)


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(TWBX) as z:
            hypers = [n for n in z.namelist() if n.endswith(".hyper")]
            z.extractall(tmp, members=hypers)
        with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
                          parameters={"log_dir": tmp}) as hp:
            for name in hypers:
                with Connection(hp.endpoint, str(Path(tmp) / name), CreateMode.NONE) as conn:
                    for table in conn.catalog.get_table_names("Extract"):
                        tname = table.name.unescaped
                        if Path(name).name == ROUTES_FILE and tname == "Extract":
                            out = "road_routes_m3.csv"
                        else:
                            out = next((f for p, f in TARGETS.items() if tname.startswith(p)), None)
                        if out is None:
                            continue
                        df = read_table(conn, table)
                        # fix Latin-1 import of "più"
                        df.columns = [c.replace("pi—", "più") for c in df.columns]
                        df.to_csv(RAW / out, index=False)
                        print(f"wrote {out:36s} {len(df):>6,} rows")


if __name__ == "__main__":
    main()
