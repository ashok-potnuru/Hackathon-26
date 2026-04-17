"""
Abstract base class that all VCS adapters must implement.
Methods to implement: clone_repo(repo), get_file(path), create_branch(name, base),
commit_changes(files, message), create_pr(PRModel), get_blame(file), get_open_prs().
To add a new VCS provider: subclass this class and implement all methods.
"""
