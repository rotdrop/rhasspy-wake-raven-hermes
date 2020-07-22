"""Hermes MQTT server for Rhasspy wakeword with Raven"""
import asyncio
import logging
import queue
import socket
import threading
import typing

from rhasspyhermes.audioserver import AudioFrame
from rhasspyhermes.base import Message
from rhasspyhermes.client import GeneratorType, HermesClient, TopicArgs
from rhasspyhermes.wake import (
    GetHotwords,
    HotwordDetected,
    HotwordError,
    HotwordExampleRecorded,
    Hotwords,
    HotwordToggleOff,
    HotwordToggleOn,
    HotwordToggleReason,
    RecordHotwordExample,
)
from rhasspysilence import WebRtcVadRecorder
from rhasspywake_raven import Raven
from rhasspywake_raven.utils import trim_silence

WAV_HEADER_BYTES = 44
_LOGGER = logging.getLogger("rhasspywake_raven_hermes")

# -----------------------------------------------------------------------------


class WakeHermesMqtt(HermesClient):
    """Hermes MQTT server for Rhasspy wakeword with Raven."""

    def __init__(
        self,
        client,
        raven: Raven,
        minimum_matches: int = 1,
        wakeword_id: str = "",
        site_ids: typing.Optional[typing.List[str]] = None,
        enabled: bool = True,
        sample_rate: int = 16000,
        sample_width: int = 2,
        channels: int = 1,
        chunk_size: int = 960,
        udp_audio: typing.Optional[typing.List[typing.Tuple[str, int, str]]] = None,
        udp_chunk_size: int = 2048,
        log_predictions: bool = False,
    ):
        super().__init__(
            "rhasspywake_raven_hermes",
            client,
            sample_rate=sample_rate,
            sample_width=sample_width,
            channels=channels,
            site_ids=site_ids,
        )

        self.subscribe(
            AudioFrame,
            HotwordToggleOn,
            HotwordToggleOff,
            GetHotwords,
            RecordHotwordExample,
        )

        self.raven = raven
        self.minimum_matches = minimum_matches
        self.wakeword_id = wakeword_id

        self.enabled = enabled
        self.disabled_reasons: typing.Set[str] = set()

        # Required audio format
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.channels = channels

        self.chunk_size = chunk_size

        # Queue of WAV audio chunks to process (plus site_id)
        self.wav_queue: queue.Queue = queue.Queue()

        self.first_audio: bool = True
        self.audio_buffer = bytes()

        self.last_audio_site_id: str = "default"

        # Fields for recording examples
        self.recording_example = False
        self.example_recorder = WebRtcVadRecorder(max_seconds=10)
        self.example_future: typing.Optional[asyncio.Future] = None

        # Start threads
        self.detection_thread = threading.Thread(
            target=self.detection_thread_proc, daemon=True
        )
        self.detection_thread.start()

        # Listen for raw audio on UDP too
        self.udp_chunk_size = udp_chunk_size

        if udp_audio:
            for udp_host, udp_port, udp_site_id in udp_audio:
                threading.Thread(
                    target=self.udp_thread_proc,
                    args=(udp_host, udp_port, udp_site_id),
                    daemon=True,
                ).start()

    # -------------------------------------------------------------------------

    async def handle_audio_frame(
        self, wav_bytes: bytes, site_id: str = "default"
    ) -> None:
        """Process a single audio frame"""
        self.wav_queue.put((wav_bytes, site_id))

    async def handle_detection(
        self, matching_indexes: typing.List[int]
    ) -> typing.AsyncIterable[
        typing.Union[typing.Tuple[HotwordDetected, TopicArgs], HotwordError]
    ]:
        """Handle a successful hotword detection"""
        try:
            template = self.raven.templates[matching_indexes[0]]
            wakeword_id = self.wakeword_id
            if not wakeword_id:
                wakeword_id = template.name

            yield (
                HotwordDetected(
                    site_id=self.last_audio_site_id,
                    model_id=template.name,
                    current_sensitivity=self.raven.distance_threshold,
                    model_version="",
                    model_type="personal",
                ),
                {"wakeword_id": wakeword_id},
            )
        except Exception as e:
            _LOGGER.exception("handle_detection")
            yield HotwordError(
                error=str(e),
                context=str(matching_indexes),
                site_id=self.last_audio_site_id,
            )

    async def handle_get_hotwords(
        self, get_hotwords: GetHotwords
    ) -> typing.AsyncIterable[typing.Union[Hotwords, HotwordError]]:
        """Report available hotwords"""
        try:
            yield Hotwords(models=[], id=get_hotwords.id, site_id=get_hotwords.site_id)

        except Exception as e:
            _LOGGER.exception("handle_get_hotwords")
            yield HotwordError(
                error=str(e), context=str(get_hotwords), site_id=get_hotwords.site_id
            )

    async def handle_record_example(
        self, record_example: RecordHotwordExample
    ) -> typing.AsyncIterable[
        typing.Union[typing.Tuple[HotwordExampleRecorded, TopicArgs], HotwordError]
    ]:
        """Record an example of a hotword."""
        try:
            assert (
                not self.recording_example
            ), "Only one example can be recorded at a time"

            # Start recording
            assert self.loop, "No loop"
            self.example_future = self.loop.create_future()
            self.example_recorder.start()
            self.recording_example = True

            # Wait for result
            _LOGGER.debug("Recording example (id=%s)", record_example.id)
            example_audio = await self.example_future
            assert isinstance(example_audio, bytes)

            # Trim silence
            _LOGGER.debug("Trimming silence from example")
            example_audio = trim_silence(example_audio)

            # Convert to WAV format
            wav_data = self.to_wav_bytes(example_audio)

            yield (
                HotwordExampleRecorded(wav_bytes=wav_data),
                {"site_id": record_example.site_id, "request_id": record_example.id},
            )

        except Exception as e:
            _LOGGER.exception("handle_record_example")
            yield HotwordError(
                error=str(e),
                context=str(record_example),
                site_id=record_example.site_id,
            )

    def add_example_audio(self, audio_data: bytes):
        """Add an audio frame to the currently recording example."""
        result = self.example_recorder.process_chunk(audio_data)
        if result:
            self.recording_example = False
            assert self.example_future is not None, "No future"
            example_audio = self.example_recorder.stop()
            _LOGGER.debug(
                "Recorded %s byte(s) for audio for example", len(example_audio)
            )

            # Signal waiting coroutine with audio
            assert self.loop, "No loop"
            self.loop.call_soon_threadsafe(
                self.example_future.set_result, example_audio
            )

    # -------------------------------------------------------------------------

    def detection_thread_proc(self):
        """Handle WAV audio chunks."""
        try:
            while True:
                wav_bytes, site_id = self.wav_queue.get()
                if wav_bytes is None:
                    # Shutdown signal
                    break

                self.last_audio_site_id = site_id

                # Handle audio frames
                if self.first_audio:
                    _LOGGER.debug("Receiving audio")
                    self.first_audio = False

                # Extract/convert audio data
                audio_data = self.maybe_convert_wav(wav_bytes)

                if self.recording_example:
                    # Add to currently recording example
                    self.add_example_audio(audio_data)

                    # Don't process audio for wake word while recording
                    self.audio_buffer = bytes()
                    continue

                # Add to persistent buffer
                self.audio_buffer += audio_data

                # Process in chunks.
                # Any remaining audio data will be kept in buffer.
                while len(self.audio_buffer) >= self.chunk_size:
                    chunk = self.audio_buffer[: self.chunk_size]
                    self.audio_buffer = self.audio_buffer[self.chunk_size :]

                    if chunk:
                        try:
                            matching_indexes = self.raven.process_chunk(chunk)
                            if len(matching_indexes) >= self.minimum_matches:
                                asyncio.run_coroutine_threadsafe(
                                    self.publish_all(
                                        self.handle_detection(matching_indexes)
                                    ),
                                    self.loop,
                                )
                        except Exception:
                            _LOGGER.exception("process_chunk")
        except Exception:
            _LOGGER.exception("detection_thread_proc")

    # -------------------------------------------------------------------------

    def udp_thread_proc(self, host: str, port: int, site_id: str):
        """Handle WAV chunks from UDP socket."""
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.bind((host, port))
            _LOGGER.debug("Listening for audio on UDP %s:%s", host, port)

            while True:
                wav_bytes, _ = udp_socket.recvfrom(
                    self.udp_chunk_size + WAV_HEADER_BYTES
                )

                if self.enabled:
                    self.wav_queue.put((wav_bytes, site_id))
        except Exception:
            _LOGGER.exception("udp_thread_proc")

    # -------------------------------------------------------------------------

    async def on_message_blocking(
        self,
        message: Message,
        site_id: typing.Optional[str] = None,
        session_id: typing.Optional[str] = None,
        topic: typing.Optional[str] = None,
    ) -> GeneratorType:
        """Received message from MQTT broker."""
        # Check enable/disable messages
        if isinstance(message, HotwordToggleOn):
            if message.reason == HotwordToggleReason.UNKNOWN:
                # Always enable on unknown
                self.disabled_reasons.clear()
            else:
                self.disabled_reasons.discard(message.reason)

            if self.disabled_reasons:
                _LOGGER.debug("Still disabled: %s", self.disabled_reasons)
            else:
                self.enabled = True
                self.first_audio = True
                _LOGGER.debug("Enabled")
        elif isinstance(message, HotwordToggleOff):
            self.enabled = False
            self.disabled_reasons.add(message.reason)
            _LOGGER.debug("Disabled")
        elif isinstance(message, AudioFrame):
            if self.enabled:
                assert site_id, "Missing site_id"
                await self.handle_audio_frame(message.wav_bytes, site_id=site_id)
        elif isinstance(message, GetHotwords):
            async for hotword_result in self.handle_get_hotwords(message):
                yield hotword_result
        elif isinstance(message, RecordHotwordExample):
            # Handled in on_message
            pass
        else:
            _LOGGER.warning("Unexpected message: %s", message)

    async def on_message(
        self,
        message: Message,
        site_id: typing.Optional[str] = None,
        session_id: typing.Optional[str] = None,
        topic: typing.Optional[str] = None,
    ) -> GeneratorType:
        """Received message from MQTT broker (non-blocking)."""
        if isinstance(message, RecordHotwordExample):
            async for example_result in self.handle_record_example(message):
                yield example_result
