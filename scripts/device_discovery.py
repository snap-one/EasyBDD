#!/usr/bin/env python3
"""
Device Discovery and Registration System
Automatically discovers devices on the network and creates appropriate configs
"""

import ipaddress
import asyncio
import aiohttp
import socket
from pathlib import Path
from typing import Dict, List, Optional
import yaml
import nmap
from datetime import datetime

class DeviceDiscovery:
    def __init__(self, config_dir: Path = Path("config")):
        self.config_dir = config_dir
        self.device_types_dir = config_dir / "device_types"
        self.devices_dir = config_dir / "devices"
        self.discovered_devices = []
        
        # Device fingerprinting patterns
        self.device_signatures = {
            "ip_camera": {
                "ports": [80, 443, 554, 8080],
                "http_headers": ["server: nginx", "server: apache", "rtsp"],
                "paths": ["/onvif", "/cgi-bin", "/streaming"],
                "keywords": ["camera", "nvr", "dvr", "hikvision", "dahua", "axis"]
            },
            "power_supply": {
                "ports": [80, 443, 161, 23],
                "http_headers": ["server: apc", "ups", "pdu"],
                "paths": ["/outlets", "/power", "/ups"],
                "keywords": ["apc", "eaton", "tripp", "pdu", "ups"]
            },
            "network_switch": {
                "ports": [80, 443, 22, 23, 161],
                "http_headers": ["cisco", "hp", "netgear", "switch"],
                "paths": ["/config", "/switch", "/ports"],
                "keywords": ["cisco", "catalyst", "procurve", "netgear", "switch"]
            }
        }
    
    async def discover_network(self, network: str = "192.168.1.0/24") -> List[Dict]:
        """Discover devices on network using multiple methods"""
        print(f"🔍 Discovering devices on {network}")
        
        # Method 1: Ping sweep
        live_hosts = await self._ping_sweep(network)
        
        # Method 2: Port scanning
        device_profiles = []
        for host in live_hosts:
            profile = await self._fingerprint_device(host)
            if profile:
                device_profiles.append(profile)
                
        return device_profiles
    
    async def _ping_sweep(self, network: str) -> List[str]:
        """Find live hosts using ping"""
        live_hosts = []
        net = ipaddress.IPv4Network(network)
        
        tasks = []
        for ip in net.hosts():
            tasks.append(self._ping_host(str(ip)))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for ip, is_alive in zip(net.hosts(), results):
            if isinstance(is_alive, bool) and is_alive:
                live_hosts.append(str(ip))
                
        print(f"📡 Found {len(live_hosts)} live hosts")
        return live_hosts
    
    async def _ping_host(self, host: str) -> bool:
        """Ping a single host"""
        try:
            proc = await asyncio.create_subprocess_exec(
                'ping', '-c', '1', '-W', '1000', host,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.wait()
            return proc.returncode == 0
        except:
            return False
    
    async def _fingerprint_device(self, host: str) -> Optional[Dict]:
        """Identify device type through various methods"""
        print(f"🔍 Fingerprinting {host}")
        
        profile = {
            "ip": host,
            "timestamp": datetime.now().isoformat(),
            "open_ports": [],
            "device_type": "unknown",
            "confidence": 0,
            "details": {}
        }
        
        # Port scan
        profile["open_ports"] = await self._scan_ports(host)
        
        # HTTP fingerprinting
        if 80 in profile["open_ports"] or 443 in profile["open_ports"]:
            http_info = await self._http_fingerprint(host)
            profile["details"].update(http_info)
            
        # SNMP fingerprinting  
        if 161 in profile["open_ports"]:
            snmp_info = await self._snmp_fingerprint(host)
            profile["details"].update(snmp_info)
            
        # Determine device type
        device_type, confidence = self._classify_device(profile)
        profile["device_type"] = device_type
        profile["confidence"] = confidence
        
        return profile if device_type != "unknown" else None
    
    async def _scan_ports(self, host: str) -> List[int]:
        """Scan common ports"""
        common_ports = [22, 23, 53, 80, 443, 161, 554, 8080, 8443]
        open_ports = []
        
        for port in common_ports:
            if await self._check_port(host, port):
                open_ports.append(port)
                
        return open_ports
    
    async def _check_port(self, host: str, port: int) -> bool:
        """Check if a port is open"""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=2
            )
            writer.close()
            await writer.wait_closed()
            return True
        except:
            return False
    
    async def _http_fingerprint(self, host: str) -> Dict:
        """Gather HTTP information"""
        http_info = {}
        
        for port in [80, 443]:
            scheme = "https" if port == 443 else "http"
            url = f"{scheme}://{host}:{port if port != 80 else ''}"
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                        http_info[f"http_{port}"] = {
                            "status": response.status,
                            "headers": dict(response.headers),
                            "server": response.headers.get("server", ""),
                            "title": await self._extract_title(response)
                        }
            except:
                continue
                
        return http_info
    
    async def _extract_title(self, response) -> str:
        """Extract HTML title"""
        try:
            text = await response.text()
            start = text.lower().find("<title>")
            end = text.lower().find("</title>")
            if start != -1 and end != -1:
                return text[start+7:end].strip()
        except:
            pass
        return ""
    
    async def _snmp_fingerprint(self, host: str) -> Dict:
        """SNMP system information"""
        # This would use pysnmp or similar
        # Simplified for demonstration
        return {"snmp": "detected"}
    
    def _classify_device(self, profile: Dict) -> tuple:
        """Classify device based on gathered information"""
        scores = {}
        
        for device_type, signatures in self.device_signatures.items():
            score = 0
            
            # Check ports
            matching_ports = set(profile["open_ports"]) & set(signatures["ports"])
            score += len(matching_ports) * 10
            
            # Check HTTP headers and content
            for port_key, info in profile["details"].items():
                if port_key.startswith("http_"):
                    server = info.get("server", "").lower()
                    title = info.get("title", "").lower()
                    
                    for keyword in signatures["keywords"]:
                        if keyword in server or keyword in title:
                            score += 20
                            
            scores[device_type] = score
        
        if scores:
            best_match = max(scores, key=scores.get)
            confidence = scores[best_match]
            return best_match, confidence
        
        return "unknown", 0
    
    async def generate_device_config(self, profile: Dict, device_name: str = None) -> Path:
        """Generate device configuration from discovery profile"""
        device_type = profile["device_type"]
        ip = profile["ip"]
        
        if not device_name:
            device_name = f"{device_type}_{ip.replace('.', '_')}"
            
        # Load device type template
        template_path = self.device_types_dir / f"{device_type}.yaml"
        with open(template_path) as f:
            template = yaml.safe_load(f)
        
        # Create device configuration
        device_config = {
            "name": f"Auto-discovered {device_type} - {ip}",
            "device_type": device_type,
            "ip_address": ip,
            "discovery_timestamp": profile["timestamp"],
            "discovery_confidence": profile["confidence"],
            "tags": ["auto_discovered", device_type],
            
            # Inherit from template
            **template["default_config"],
            
            # Override with discovered values
            "network": {
                **template["default_config"]["network"],
                "device_ip": ip,
                "base_url": f"http://{ip}"
            }
        }
        
        # Add device-specific discovered information
        if device_type == "ip_camera" and 554 in profile["open_ports"]:
            device_config["protocols"] = template["default_config"]["protocols"]
            
        # Save configuration
        config_path = self.devices_dir / f"{device_name}.yaml"
        with open(config_path, "w") as f:
            yaml.dump(device_config, f, default_flow_style=False)
            
        print(f"✅ Generated config: {config_path}")
        return config_path


async def main():
    """Example usage"""
    discovery = DeviceDiscovery()
    
    # Discover devices
    devices = await discovery.discover_network("192.168.1.0/24")
    
    print(f"\\n📋 Discovery Results:")
    for device in devices:
        print(f"  {device['ip']}: {device['device_type']} (confidence: {device['confidence']})")
        
        # Generate configuration
        config_path = await discovery.generate_device_config(device)
        print(f"    Config: {config_path}")


if __name__ == "__main__":
    asyncio.run(main())