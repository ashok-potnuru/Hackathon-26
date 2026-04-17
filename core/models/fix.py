"""
Defines FixModel, which represents a generated code fix ready for PR creation.
Fields: files_changed, diff, reasoning, regression_test, security_scan_passed,
lint_passed, confidence_score. Passed from fix_generator to pr_creator.
"""
