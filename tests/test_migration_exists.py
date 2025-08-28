import os

def test_migration_exists():
    assert os.path.exists('migrations/versions/0034_prework_account_invite.py')
