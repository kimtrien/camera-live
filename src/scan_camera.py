import logging
import socket
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import netifaces
import scapy.all as scapy

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_default_gateway_interface():
    """Returns the interface name dependent on the default gateway."""
    try:
        gws = netifaces.gateways()
        return gws['default'][netifaces.AF_INET][1]
    except (KeyError, IndexError):
        return None

def get_local_network_info():
    """
    Retrieves the local IP and subnet mask for the default interface.
    Returns a string in CIDR notation (e.g., '192.168.1.0/24') or None.
    """
    interface = get_default_gateway_interface()
    if not interface:
        logger.error("Could not determine default interface.")
        return None
    
    try:
        addrs = netifaces.ifaddresses(interface)
        if netifaces.AF_INET in addrs:
            # Taking the first IPv4 address found on the interface
            ip_info = addrs[netifaces.AF_INET][0]
            ip_addr = ip_info.get('addr')
            netmask = ip_info.get('netmask')
            
            if ip_addr and netmask:
                # Calculate CIDR prefix length from netmask
                cidr = sum([bin(int(x)).count('1') for x in netmask.split('.')])
                
                # Calculate network address using IP and netmask
                ip_parts = [int(x) for x in ip_addr.split('.')]
                mask_parts = [int(x) for x in netmask.split('.')]
                net_parts = [i & m for i, m in zip(ip_parts, mask_parts)]
                network_addr = ".".join(map(str, net_parts))
                
                logger.info(f"Detected Local IP: {ip_addr} on interface {interface}")
                logger.info(f"Network: {network_addr}/{cidr}")
                return f"{network_addr}/{cidr}"
    except Exception as e:
        logger.error(f"Error getting network info: {e}")
    
    return None

def scan_arp(ip_range):
    """
    Performs an ARP scan on the specified IP range.
    Returns a list of dictionaries with 'ip' and 'mac'.
    """
    logger.info(f"Starting ARP scan on {ip_range}...")
    try:
        # scapy.arping returns a tuple (answered, unanswered)
        # answered is a list of (sent_packet, received_packet)
        answered, _ = scapy.arping(ip_range, verbose=False, timeout=2)
        devices = []
        for sent, received in answered:
            devices.append({'ip': received.psrc, 'mac': received.hwsrc})
        logger.info(f"ARP scan complete. Found {len(devices)} devices.")
        return devices
    except Exception as e:
        logger.error(f"Error during ARP scan: {e}")
        return []

def check_port(ip, port, timeout=1):
    """
    Checks if a specific port is open on a given IP.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((ip, port))
            if result == 0:
                return True
    except Exception:
        pass
    return False

def scan_cameras(devices):
    """
    Scans the list of devices for open RTSP port (554).
    """
    logger.info("Scanning for camera ports (RTSP - 554)...")
    cameras = []
    
    def check_device(device):
        ip = device['ip']
        if check_port(ip, 554):
            logger.info(f"[MATCH] Possible Camera found at {ip} ({device['mac']}) - Port 554 OPEN")
            device['type'] = 'Camera (RTSP 554 Open)'
            cameras.append(device)
        elif check_port(ip, 80) or check_port(ip, 8080):
             # Less specific, but could be a camera web UI
             # Verify if 554 failed but this opened, might be a camera with RTSP disabled or non-standard
             pass

    with ThreadPoolExecutor(max_workers=20) as executor:
        executor.map(check_device, devices)
    
    return cameras

def main():
    logger.info("--- Camera Scanner Started ---")
    
    network = get_local_network_info()
    if not network:
        logger.error("Failed to detect local network. Exiting.")
        sys.exit(1)
        
    devices = scan_arp(network)
    if not devices:
        logger.warning("No devices found on the network. Check permissions (sudo might be required).")
        sys.exit(0)
        
    cameras = scan_cameras(devices)
    
    print("\n" + "="*40)
    print("SCAN RESULTS")
    print("="*40)
    
    if cameras:
        for cam in cameras:
            print(f"FOUND CAMERA: IP: {cam['ip']}\tMAC: {cam['mac']}")
    else:
        print("No cameras detected with open RTSP port (554).")
        print(f"Total devices found: {len(devices)}")
        for dev in devices:
             print(f"Device: {dev['ip']} - {dev['mac']}")

    print("="*40 + "\n")

if __name__ == "__main__":
    main()
