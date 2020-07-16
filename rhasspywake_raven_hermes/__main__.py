"""Hermes MQTT service for Rhasspy wakeword with Raven"""
import argparse
import asyncio
import logging
import typing
from pathlib import Path

import paho.mqtt.client as mqtt
import rhasspyhermes.cli as hermes_cli
from rhasspywake_raven import Raven

from . import WakeHermesMqtt

_DIR = Path(__file__).parent
_LOGGER = logging.getLogger("rhasspywake_raven_hermes")

# -----------------------------------------------------------------------------


def main():
    """Main method."""
    parser = argparse.ArgumentParser(prog="rhasspy-wake-raven-hermes")
    parser.add_argument(
        "--template-dir", required=True, help="Directories with Raven WAV templates"
    )
    parser.add_argument(
        "--distance-threshold",
        type=float,
        required=True,
        help="Normalized dynamic time warping distance threshold for template matching",
    )
    parser.add_argument(
        "--wakeword-id",
        default="",
        help="Wakeword ID for model (default: use file name)",
    )
    parser.add_argument(
        "--udp-audio",
        nargs=3,
        action="append",
        help="Host/port/siteId for UDP audio input",
    )
    parser.add_argument(
        "--log-predictions",
        action="store_true",
        help="Log prediction probabilities for each audio chunk (very verbose)",
    )

    hermes_cli.add_hermes_args(parser)
    args = parser.parse_args()

    hermes_cli.setup_logging(args)
    _LOGGER.debug(args)
    hermes: typing.Optional[WakeHermesMqtt] = None

    args.template_dir = Path(args.template_dir)

    _LOGGER.debug("Loading WAV templates from %s", args.template_dir)
    templates = [
        Raven.wav_to_template(p, name=p.name) for p in args.template_dir.glob("*.wav")
    ]
    raven = Raven(
        templates=templates,
        distance_threshold=args.distance_threshold,
        debug=args.log_predictions,
    )

    udp_audio = []
    if args.udp_audio:
        udp_audio = [
            (host, int(port), site_id) for host, port, site_id in args.udp_audio
        ]

    # Listen for messages
    client = mqtt.Client()
    hermes = WakeHermesMqtt(
        client,
        raven=raven,
        wakeword_id=args.wakeword_id,
        udp_audio=udp_audio,
        site_ids=args.site_id,
    )

    _LOGGER.debug("Connecting to %s:%s", args.host, args.port)
    hermes_cli.connect(client, args)
    client.loop_start()

    try:
        # Run event loop
        asyncio.run(hermes.handle_messages_async())
    except KeyboardInterrupt:
        pass
    finally:
        _LOGGER.debug("Shutting down")
        client.loop_stop()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    main()
