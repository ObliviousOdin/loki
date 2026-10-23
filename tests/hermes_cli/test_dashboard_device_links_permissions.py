"""Check native filesystem protection, not synthetic POSIX mode bits on Windows."""
import pytest

pytest_plugins = ('tests.hermes_cli.test_dashboard_device_links_store',)


@pytest.mark.platforms('macos', 'linux')
def test_device_store_posix_permissions(phone_store):
    store, _, _ = phone_store
    assert (store.path.stat().st_mode & 0o777) == 0o600
    assert (store.path.parent.stat().st_mode & 0o777) == 0o700


@pytest.mark.platforms('windows')
def test_device_store_windows_dacl_excludes_other_users(phone_store):
    import win32api
    import win32security

    store, _, _ = phone_store
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)
    try:
        user = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        win32api.CloseHandle(token)
    allowed = {win32security.ConvertSidToStringSid(user), 'S-1-5-18', 'S-1-5-32-544', 'S-1-3-4'}
    for path in (store.path.parent, store.path):
        descriptor = win32security.GetFileSecurity(str(path), win32security.DACL_SECURITY_INFORMATION)
        dacl = descriptor.GetSecurityDescriptorDacl()
        assert dacl is not None and dacl.GetAceCount() > 0
        for index in range(dacl.GetAceCount()):
            ace = dacl.GetAce(index)
            assert ace[0][0] == win32security.ACCESS_ALLOWED_ACE_TYPE
            assert win32security.ConvertSidToStringSid(ace[2]) in allowed
        if path.is_dir():
            # CPython >=3.13's mkdir(mode=0700) protects the DACL from inherited broad grants.
            assert descriptor.GetSecurityDescriptorControl()[0] & win32security.SE_DACL_PROTECTED
