"""Wake-on-LAN service — sends a magic packet over UDP broadcast."""

import socket
import time


class WoLService:
    """Send Wake-on-LAN magic packets.

    Supported action:
        wol.send   — broadcast a magic packet to the given MAC address

    Parameters:
        mac         : MAC address of the target device (required).
                      Accepts XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX format.
                      Falls back to the 'mac_for_report' suite variable if omitted.
        broadcast   : broadcast address to use (default: 255.255.255.255)
        port        : UDP port (default: 9)
        sleep       : seconds to wait after sending (default: 5)
        store_as    : variable name to store the result message in
    """

    def execute(self, action: str, params: dict, variables: dict):
        action_lower = action.lower()
        if action_lower in ("wol.send", "wol.wake", "wol"):
            return self._send(params, variables)
        raise ValueError(f"Unknown wol action: '{action}'. Use 'wol.send'.")

    def _send(self, params: dict, variables: dict) -> str:
        mac = params.get("mac") or variables.get("mac_for_report", "")
        if not mac:
            raise ValueError("wol.send requires 'mac' parameter or 'mac_for_report' variable")

        broadcast = params.get("broadcast", "255.255.255.255")
        port = int(params.get("port", 9))
        sleep_secs = float(params.get("sleep", 5))

        mac_hex = mac.replace(":", "").replace("-", "").upper()
        if len(mac_hex) != 12:
            raise ValueError(f"Invalid MAC address: '{mac}'")

        magic_packet = bytes.fromhex("FF" * 6 + mac_hex * 16)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic_packet, (broadcast, port))

        if sleep_secs > 0:
            time.sleep(sleep_secs)

        return f"WoL packet sent to {mac}"
