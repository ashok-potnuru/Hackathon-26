"""
Pulls jobs from the queue and runs the full pipeline for each job.
Implements retry logic and dead-letter queue routing on repeated failure.
On unrecoverable failures, notifies Teams and updates Zoho — never swallow errors silently.
"""
