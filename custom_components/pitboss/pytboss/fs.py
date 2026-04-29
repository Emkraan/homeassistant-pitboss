"""Client library for Mongoose OS filesystem RPCs."""

from base64 import b64decode

from .transport import Transport


class FileSystem:
    """Client library for Mongoose OS filesystem RPCs."""

    def __init__(self, conn: Transport) -> None:
        self._conn = conn

    async def get_file_list(self) -> dict:
        return await self._conn.send_command("FS.List", {})

    async def get_file_content(self, filename) -> str:
        length = 512
        offset = 0
        content = ""
        while True:
            resp = await self._conn.send_command(
                "FS.Get", {"filename": filename, "offset": offset, "len": length}
            )
            content += str(b64decode(resp["data"]))
            offset += length
            if resp["left"] == 0:
                return content

    async def set_file_content(self, filename, data, append) -> dict:
        return await self._conn.send_command(
            "FS.Put",
            {"filename": filename, "data": data, "append": append},
        )

    async def rename_file(self, src, dst) -> dict:
        return await self._conn.send_command("FS.Rename", {"src": src, "dst": dst})

    async def delete_file(self, filename) -> dict:
        return await self._conn.send_command("FS.Remove", {"filename": filename})
