Put UAE government open-data CSVs here.

Dubai Land Department transactions (Data.Dubai / Dubai Pulse, open dataset):
  data.dubai  ->  Dubai Land Department  ->  Transactions  ->  export CSV
Save as e.g. dld_transactions.csv in this folder, then run:
  python3 -m pipeline.gov_data        (re-prices the loan book from DLD median AED per m2; no internet needed)
The real pipeline (RUN_PIPELINE_*) also picks it up automatically.
