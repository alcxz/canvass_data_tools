-- Require every household to have a Dissemination Area.
--
-- A household with a NULL dauid cannot appear in any aggregate: every query in
-- backend/queries.py joins households to census_da through it. Such a row would
-- sit in the table looking like data while being invisible in the map, the DA
-- detail panel and the voter list alike.
--
-- Doors that cannot be geocoded now stay out of the database entirely and are
-- written to data/unmatched_addresses.csv for manual correction, covering both
-- failure modes: no matching address point, and geocoded outside the ward.
--
-- Their canvass rows are skipped by import_canvass.py until the address is
-- fixed. That is a deliberate trade of completeness for cleanliness -- on the
-- Aug 6 export it holds back 246 doors carrying 248 canvass rows, 74 of which
-- have a support level. Re-run both scripts after correcting addresses.

begin;

-- Safe on the current database (households is empty), and correct in general:
-- these rows could never have been queried anyway.
delete from households where dauid is null;

alter table households alter column dauid set not null;

-- geocode_status now only ever takes one value, since anything else is not
-- inserted. Kept as a column rather than dropped so a future inference pass can
-- reintroduce a value such as 'inferred' without a table rewrite.
update households set geocode_status = 'matched' where geocode_status <> 'matched';

alter table households drop constraint households_geocode_status_check;

alter table households
    add constraint households_geocode_status_check
    check (geocode_status in ('matched'));

alter table households alter column geocode_status set default 'matched';

commit;
