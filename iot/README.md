# IoT field nodes

Notes for building the physical monitoring nodes that report to
`POST /api/v1/sensors/readings` (see [`docs/api/README.md`](../docs/api/README.md)
and `backend/app/services/sensor_service.py`).

## Node types

| `kind` | Typical hardware | Reports |
|---|---|---|
| `CAMERA_TRAP` | ESP32-CAM or Raspberry Pi + camera, PIR trigger | images, uploaded via `POST /observations/capture` on a paired app or gateway |
| `ACOUSTIC_RECORDER` | ESP32/Pi + I2S MEMS microphone | recordings, same path as above |
| `ENV_SENSOR` / `MULTI_SENSOR_NODE` | ESP32 + DHT22/BME280 (temp/humidity), LDR (light), PIR (motion) | `POST /sensors/readings` directly |

A camera trap or acoustic recorder generally cannot itself call the
observation-capture endpoint (no field connectivity, or it needs an operator
to confirm species/location) — the usual pattern is the node writes to local
storage or a gateway, and a researcher uploads the capture through the app.
An environmental node has no such judgement call to make, so it reports
readings directly and continuously.

## Registration flow

```
Forest officer                    Node
      │                             │
      │  POST /sensors/devices      │
      │ ───────────────────────▶    │
      │  { device_code,             │
      │    ingest_key }  ◀───────── │  (shown once — copy into firmware config)
      │                             │
      │                             │  POST /sensors/readings
      │                             │  { device_code, ingest_key, readings: [...] }
      │                             │ ───────────────────────▶
```

The ingest key authenticates the node — see
[`docs/architecture/security.md`](../docs/architecture/security.md#devices).
It is never shown again after registration; use
`POST /sensors/devices/{id}/rotate-key` if it is lost or compromised.

## `firmware/`

Reference notes for an ESP32-based multi-sensor node: wiring, the reporting
loop, and the JSON payload shape expected by `SensorBatchIn`
(`backend/app/schemas/iot.py`). Not a build system — adapt to your own
toolchain (Arduino, ESP-IDF, MicroPython).

## `device-config/`

Example device configuration (reporting interval, sensor pin mapping) as
JSON, matching `DeviceCreate` in `backend/app/schemas/iot.py`.
