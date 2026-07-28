/**
 * Static list of synthetic customers used to populate the IDLE-state PAN
 * dropdown. The 23 entries mirror the customer rows in
 * `build_docs/cibil_data.json` — kept inline so the frontend has no runtime
 * dependency on the backend for demo selection. If the seed file changes,
 * regenerate this list from `python scripts/seed_db.py --print-customers`.
 *
 * Because this is a portfolio project and the data is intentionally
 * synthetic, the full PAN + first_name is rendered together to make picking
 * the right record easy.
 */
export interface CustomerOption {
  /** 10-character PAN card number, e.g. "ABCPS1234A". */
  pan_card: string;
  /** Synthetic first name shown alongside the PAN. */
  first_name: string;
}

export const CUSTOMERS: ReadonlyArray<CustomerOption> = [
  { pan_card: 'ABCPS1234A', first_name: 'Anjali' },
  { pan_card: 'BCDRM2345B', first_name: 'Carlos' },
  { pan_card: 'CDEPI3456C', first_name: 'Priya' },
  { pan_card: 'DEFPC4567D', first_name: 'Lin' },
  { pan_card: 'EFGKD5678E', first_name: 'Marcus' },
  { pan_card: 'FGHPJ6789F', first_name: 'Divya' },
  { pan_card: 'GHIPK7890G', first_name: 'Rohan' },
  { pan_card: 'HIJPL8901H', first_name: 'Sana' },
  { pan_card: 'IJKPM9012I', first_name: 'Vikram' },
  { pan_card: 'JKLPN0123J', first_name: 'Meera' },
  { pan_card: 'KLMPO1234K', first_name: 'Arjun' },
  { pan_card: 'LMNPP2345L', first_name: 'Farah' },
  { pan_card: 'MNOPQ3456M', first_name: 'Kabir' },
  { pan_card: 'NOPPR4567N', first_name: 'Tara' },
  { pan_card: 'OPQPS5678O', first_name: 'Dev' },
  { pan_card: 'PQRPT6789P', first_name: 'Nisha' },
  { pan_card: 'QRSPU7890Q', first_name: 'Aman' },
  { pan_card: 'RSTPV8901R', first_name: 'Ishita' },
  { pan_card: 'STUPW9012S', first_name: 'Zoya' },
  { pan_card: 'TUVPX0123T', first_name: 'Karan' },
  { pan_card: 'UVWPY1234U', first_name: 'Riya' },
  { pan_card: 'VWXPZ2345V', first_name: 'Sameer' },
  { pan_card: 'WXYQA3456W', first_name: 'Anaya' },
];
