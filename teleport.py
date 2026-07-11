# Original work Copyright (c) 2021 Alexander Henne
# Modified work Copyright (c) 2026 Jeff Nedley
# Licensed under the MIT License (see LICENSE for details)

import asyncio
import logging
import requests
import subprocess
import uuid
import socket

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceServer, RTCConfiguration
from aiortc.sdp import grouplines, parse_attr

from platform_utils import find_wg, subprocess_kwargs

ICE_STUN_SERVER = "stun:global.stun.twilio.com:3478"

REQUEST_DEVICE_TOKEN_URL = "https://client.amplifi.com/api/deviceToken/mlRequestClientAccess"
ICE_CONFIG_URL = "https://client.amplifi.com/api/deviceToken/mlIceConfig"
SIGNALING_URL = "https://client.amplifi.com/api/deviceToken/mlClientConnect"

# AmpliFi's API expects a mobile platform label (controls router UI icon / handshake).
# Do not send "macOS"/"Windows" — that can cause connect failures (e.g. error 10).
DEVICE_PLATFORM = "iOS"

# Human-readable hints for known AmpliFi API error codes
_API_ERROR_HINTS = {
    10: (
        "AmpliFi rejected the Teleport handshake (error 10). "
        "Make sure you are NOT on your AmpliFi home Wi‑Fi (use cellular or another network), "
        "and that your Teleport PIN is still valid."
    ),
}

logger = logging.getLogger("AmpliFi Teleport for Desktop")


def _generate_wg_keys():
    wg = find_wg()
    if not wg:
        raise Exception("WireGuard 'wg' tool not found. Install WireGuard and ensure wg is on PATH.")

    kwargs = subprocess_kwargs()
    private_key = subprocess.check_output(
        [wg, "genkey"], encoding="utf8", **kwargs
    ).strip()

    public_key_process = subprocess.Popen(
        [wg, "pubkey"],
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
        encoding="utf8",
        **kwargs,
    )
    public_key = public_key_process.communicate(input=private_key)[0].strip()
    return private_key, public_key


def _get_device_name():
    return socket.gethostname()

def _make_request_headers(token):
    return {
        "x-devicetoken": token,
        "user-agent": "AmpliFiTeleport/7 CFNetwork/1220.1 Darwin/20.3.0",
    }

def _add_tunnel_info(sdp, friendlyName, platform, publicKey):
    parts = sdp.partition("s=-")
    info = "\r\n".join([
        f"a=tool:ubnt_webrtc version ",
        f"a=uca_acf5_amplifi_friendly_name:" + friendlyName,
        f"a=uca_acf5_amplifi_nomination_mode:slave",
        f"a=uca_acf5_amplifi_platform:" + platform,
        f"a=uca_acf5_amplifi_tunnel_pub_key:" + publicKey])
    return parts[0] + parts[1] + "\r\n" + info + parts[2]

def _get_remote_description(localDescription, deviceToken):
    headers = _make_request_headers(deviceToken)

    iceConfigResponse = requests.post(ICE_CONFIG_URL, headers=headers)

    logger.debug("Raw ICE config response: %s" % iceConfigResponse.text)

    iceConfig = iceConfigResponse.json()

    if not iceConfig["success"]:
        if iceConfig["error"]:
            raise Exception("ICE config request failed (%s)" % iceConfig["error"])
        else:
            raise Exception("ICE config request failed")

    iceServers = iceConfig["servers"]

    connectResponse = requests.post(
        SIGNALING_URL,
        json={
            "iceServers": iceServers,
            "offer": localDescription
        },
        headers=headers)

    logger.debug("Raw connect response: %s" % connectResponse.text)

    answerAndSuccess = connectResponse.json()

    if not answerAndSuccess["success"]:
        err = answerAndSuccess.get("error")
        hint = _API_ERROR_HINTS.get(err) or _API_ERROR_HINTS.get(str(err))
        if hint:
            raise Exception(hint)
        if err:
            raise Exception("Connect request failed (%s)" % err)
        raise Exception("Connect request failed")

    answer = answerAndSuccess["answer"]
    return RTCSessionDescription(sdp=answer, type="answer")

def _generate_wg_config(pc, remoteDescription, privateKey):
    iceTransport = pc.sctp.transport.transport
    iceGatherer = iceTransport.iceGatherer
    connection = iceGatherer._connection

    logger.debug("Nominated peers: %s" % connection._nominated)

    if 1 not in connection._nominated:
        raise Exception("No nominated candidate peer")

    candidatePair = connection._nominated[1]

    logger.debug("Chosen candidate pair: %s" % candidatePair)

    localAddr = candidatePair.local_addr
    localPort = localAddr[1]

    remoteAddr = candidatePair.remote_addr
    remoteIp = remoteAddr[0]
    remotePort = remoteAddr[1]

    remoteSdp = remoteDescription.sdp
    session, _ = grouplines(remoteSdp)

    for line in session:
        if line.startswith("a="):
            attr, value = parse_attr(line)
            if attr == "uca_acf5_amplifi_ipv4_addr":
                interfaceAddress = value
            elif attr == "uca_acf5_amplifi_ipv4_dns_addr0":
                dnsAddress = value
            elif attr == "uca_acf5_amplifi_tunnel_pub_key":
                remotePublicKey = value

    wgConfigLines = [
        "[Interface]",
        "PrivateKey = %s" % privateKey,
        "ListenPort = %s" % localPort,
        "Address = %s/32" % interfaceAddress,
        "DNS = %s" % dnsAddress,
        "",
        "[Peer]",
        "PublicKey = %s" % remotePublicKey,
        "AllowedIPs = 0.0.0.0/0, ::/0", # Block untunneled traffic (kill-switch)
        "Endpoint = %s:%s"  % (remoteIp, remotePort)
    ]

    return "\n".join(wgConfigLines)

async def _connect_device_peer(pc, deviceToken):
    # A media channel or data channel is required
    # to create an offer, but it will not be used.
    pc.createDataChannel("chat")

    await pc.setLocalDescription(await pc.createOffer())

    privateKey, publicKey = _generate_wg_keys()
    deviceName = _get_device_name()
    platform = DEVICE_PLATFORM

    localDescription = _add_tunnel_info(
        pc.localDescription.sdp, deviceName, platform, publicKey)

    logger.debug("Sending local description: %s" % localDescription)

    try:
        remoteDescription = _get_remote_description(localDescription, deviceToken)

        logger.debug("Received remote description: %s" % remoteDescription)

        loop = asyncio.get_event_loop()
        configFuture = loop.create_future()

        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            logger.debug("ICE connection state is %s" % pc.iceConnectionState)

            if pc.iceConnectionState == "completed":
                try:
                    wgConfig = _generate_wg_config(pc, remoteDescription, privateKey)

                    logger.info("WireGuard config has been generated")
                    await pc.close()
                    configFuture.set_result(wgConfig)
                except Exception as e:
                    logger.error(e)
                    await pc.close()
                    configFuture.set_exception(e)

        await pc.setRemoteDescription(remoteDescription)

        return await configFuture
    except Exception as e:
        logger.error(e)
        await pc.close()
        raise

def generate_client_hint():
    return str(uuid.uuid4()).upper()

def get_device_token(clientHint, pin):
    clientAccessResponse = requests.post(
        REQUEST_DEVICE_TOKEN_URL,
        json={
            "client_hint": clientHint 
        },
        headers=_make_request_headers(pin))

    logger.debug("Raw client access response: %s" % clientAccessResponse.text)

    deviceTokenAndSuccess = clientAccessResponse.json()

    if not deviceTokenAndSuccess["success"]:
        if deviceTokenAndSuccess["error"]:
            raise Exception("Client access request failed (%s)" % deviceTokenAndSuccess["error"])
        else:
            raise Exception("Client access request failed")

    return deviceTokenAndSuccess["client_id"]

def connect_device(deviceToken):
    stun = RTCIceServer(urls=ICE_STUN_SERVER)
    config = RTCConfiguration([stun])
    pc = RTCPeerConnection(config)

    coro = _connect_device_peer(pc, deviceToken)

    loop = asyncio.get_event_loop()
    try:
        return loop.run_until_complete(coro)  
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(pc.close())
