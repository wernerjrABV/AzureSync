import base64
import binascii
import ctypes
from ctypes import wintypes
from typing import Protocol

CRYPTPROTECT_UI_FORBIDDEN = 0x1
_DECRYPTION_ERROR = "stored credential cannot be decrypted"


class CredentialProtectionError(RuntimeError):
    pass


class CredentialProtector(Protocol):
    def protect(self, plaintext: str) -> str: ...

    def unprotect(self, protected_value: str) -> str: ...


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


class DpapiCredentialProtector:
    def protect(self, plaintext: str) -> str:
        plaintext_bytes = plaintext.encode("utf-8")
        in_blob = self._blob_from_bytes(plaintext_bytes)
        out_blob = _DATA_BLOB()

        if not self._crypt_protect_data(ctypes.byref(in_blob), ctypes.byref(out_blob)):
            raise CredentialProtectionError(_DECRYPTION_ERROR)

        try:
            protected_bytes = self._copy_blob_bytes(out_blob)
        finally:
            self._local_free(out_blob.pbData)

        return base64.b64encode(protected_bytes).decode("ascii")

    def unprotect(self, protected_value: str) -> str:
        try:
            protected_bytes = base64.b64decode(protected_value, validate=True)
        except (binascii.Error, ValueError):
            raise CredentialProtectionError(_DECRYPTION_ERROR) from None

        in_blob = self._blob_from_bytes(protected_bytes)
        out_blob = _DATA_BLOB()

        if not self._crypt_unprotect_data(ctypes.byref(in_blob), ctypes.byref(out_blob)):
            raise CredentialProtectionError(_DECRYPTION_ERROR)

        try:
            plaintext_bytes = self._copy_blob_bytes(out_blob)
        finally:
            self._local_free(out_blob.pbData)

        try:
            return plaintext_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise CredentialProtectionError(_DECRYPTION_ERROR) from None

    @staticmethod
    def _blob_from_bytes(value: bytes) -> _DATA_BLOB:
        if not value:
            return _DATA_BLOB(0, None)

        buffer = ctypes.create_string_buffer(value)
        blob = _DATA_BLOB(
            len(value),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
        )
        blob._buffer = buffer
        return blob

    @staticmethod
    def _copy_blob_bytes(blob: _DATA_BLOB) -> bytes:
        if not blob.cbData:
            return b""
        return ctypes.string_at(blob.pbData, blob.cbData)

    @staticmethod
    def _crypt_protect_data(in_blob, out_blob) -> bool:
        crypt32 = DpapiCredentialProtector._get_crypt32()
        return bool(
            crypt32.CryptProtectData(
                in_blob,
                None,
                None,
                None,
                None,
                CRYPTPROTECT_UI_FORBIDDEN,
                out_blob,
            )
        )

    @staticmethod
    def _crypt_unprotect_data(in_blob, out_blob) -> bool:
        crypt32 = DpapiCredentialProtector._get_crypt32()
        return bool(
            crypt32.CryptUnprotectData(
                in_blob,
                None,
                None,
                None,
                None,
                CRYPTPROTECT_UI_FORBIDDEN,
                out_blob,
            )
        )

    @staticmethod
    def _local_free(pointer) -> None:
        if pointer:
            DpapiCredentialProtector._get_kernel32().LocalFree(pointer)

    @staticmethod
    def _get_crypt32():
        crypt32 = ctypes.windll.crypt32
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB),
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DATA_BLOB),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DATA_BLOB),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        return crypt32

    @staticmethod
    def _get_kernel32():
        kernel32 = ctypes.windll.kernel32
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        return kernel32
