export interface DASummary {
  dauid: string
  total_private_dwellings: number
  doors_total: number
  doors_knocked: number
  attempts: number
  doors_with_support: number
  avg_support: number | null
  coverage_pct: number | null
}

export interface Census {
  dauid: string
  population: number
  total_private_dwellings: number
  average_household_size: number
  low_income_prevalence: number
  owner: number
  renter: number
  commute_car: number
  commute_transit: number
  commute_walk: number
  commute_bike: number
  leave_0500: number
  leave_0600: number
  leave_0700: number
  leave_0800: number
  leave_0900: number
  leave_1200: number
}

export interface DADetail {
  dauid: string
  census: Census
  support_levels: { support_level: number | null; doors: number }[]
  outcome_combinations: { combination: string; attempts: number }[]
  outcome_atoms: { outcome: string; attempts: number }[]
  doors_knocked: number
}

export interface Voter {
  id: number
  name: string | null
  email: string | null
  phone: string | null
  address: string
  unit: string
  support_level: number | null
  last_attempted_on: string | null
}

/** 1:1 with canvass_attempts.support_level. Derived here, not stored --
 *  the export's redundant "Support Label" column is dropped at import. */
export const SUPPORT_LABELS: Record<number, string> = {
  1: 'Opposing',
  2: 'Leaning Against',
  3: 'Undecided',
  4: 'Leaning For',
  5: 'Supportive',
}

export const SUPPORT_COLORS: Record<string, string> = {
  '1': '#b91c1c',
  '2': '#ea580c',
  '3': '#a1a1aa',
  '4': '#65a30d',
  '5': '#15803d',
  none: '#e4e4e7',
}
