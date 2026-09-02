# Test fixtures

**Nothing in this directory is committed.** It is gitignored except for this
README, because the repository is public and these files derive from campaign
canvassing data.

Drop the following here to run the golden DA test
(`pytest tests/test_da_mapping.py`). Without them the test skips with a message
naming the missing file.

### `da_golden.csv` (required)

The "Subset of Canvasses By DA for Alex's Test" export. Columns:

```
Address,Unit,DA
"18 Page Street, Toronto, Ontario M6G 1J2, Canada",,1023
```

`DA` is the trailing 4 digits of the DAUID, not the full identifier, and a
spreadsheet has usually stripped its leading zeros. `geodata.dauid_from_da_column`
expands it back to `3520` + 4 digits.

### `address_points_subset.csv` (optional)

A cut of the City of Toronto Address Points file covering only the addresses in
`da_golden.csv`, so the test runs in seconds rather than indexing 500k rows. If
absent, the test falls back to the full `data/toronto_address_points.csv`.

Source: City of Toronto Open Data, *Address Points (Municipal) — Toronto One
Address Repository*, Open Government Licence – Toronto. Download the WGS84
(lat/long) variant.
