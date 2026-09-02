# Google Drive Files Needed (To be downloaded):

## Census-Data-by-DA

Relevant Columns:

- GEOUID (to be safe)  
- DA  
- Population  
- Total Private Dwelling  
- Average Household Size  
- Prevalence of low income  
- Owner  
- Renter  
- Car, truck or van  
- Public transit  
- Walked  
- Bicycle  
- Time leaving for work \- Between 5 a.m. and 5:59 a.m.  
- Time leaving for work \- Between 6 a.m. and 6:59 a.m.  
- Time leaving for work \- Between 7 a.m. and 7:59 a.m.  
- Time leaving for work \- Between 8 a.m. and 8:59 a.m.  
- Time leaving for work \- Between 9 a.m. and 11:59 a.m.  
- Time leaving for work \- Between 12 p.m. and 4:59 a.m.

## Voter's List \- WORKING (Aug 6\)

Relevant Columns:

- Address  
- **DA (I need to make a script to convert address to DA)**  
- Unit  
- Outcome (Array of string)  
- Support Level  
- Resident Name  
- Resident Email  
- Resident Phone  
- Date  
- Opposing Candidate

# Architecture:

## Stack

Frontend: React on Vercel probably  
Backend: FastAPI/Python/pandas on Render  
Database: Supabase

## Database Schema

### Census Data Table:

* DAUID  
* GEO UID (might be useless)  
* Population  
* Total Private Dwellings  
* Average Household Size  
* Prevalence of low income (index; it looks like a one point decimal i.e. 5.2)  
* Owner  
* Renter  
* \# Car, truck or van commuters  
* \# Public transit commuters  
* \# Walked commuters  
* \# Bicycle commuters  
* \# of ppl’s Time leaving for work \- Between 5 a.m. and 5:59 a.m.  
* \# of ppl’s Time leaving for work \- Between 6 a.m. and 6:59 a.m.  
* \# of ppl’s Time leaving for work \- Between 7 a.m. and 7:59 a.m.  
* \# of ppl’s Time leaving for work \- Between 8 a.m. and 8:59 a.m.  
* \# of ppl’s Time leaving for work \- Between 9 a.m. and 11:59 a.m.  
* \# of ppl’s Time leaving for work \- Between 12 p.m. and 4:59 a.m.

### Canvass Results Table

* Address  
* Unit  
* DA  
* Outcome (Array of string)  
* Support Level  
* Date

For this table, on unique conflict (Address \+ Unit), we will update Outcome, support level, date

### Voters Table (Should be more private)

* Address  
* DA  
* Unit  
* Resident Name  
* Resident Email  
* Resident Phone

# Supplemental Code:

## Database Insert

1. Find or download updated files from drive. (have constants for the filename)  
2. Insert new rows into the database

## DAUID Attaching

1. Find or download updated files from drive (just voter’s list file)  
2. Go through each address and add its DAUID to a new column

# Usage:

* Campaign managers for the ward 11 (University-Rosedale in Toronto) will use this app to visualize census and canvassing data throughout the ward.   
* Auth for users–No basic sign up, should only be used by people allowed since there is voter data  
* There will be a map with an overlay of all the dissemination areas (DAs). The user will click on a DA and it will highlight.   
* Clicking on a DA will send that DA’s DAUID in a request to the backend. The backend will retrieve the census data (basically all columns except DAUID and GEOUID) and the canvassing aggregates (Support level in a pie graph; 1-5 \+ no response for null, \# doors knocked, Outcomes in a pie graph). These will show up in the whitespace to the right of the map.  
* Also under the census and canvassing data will be a button that says show voter list, this will query the voters database and return their information plus their support level and display it in a table on the frontend.