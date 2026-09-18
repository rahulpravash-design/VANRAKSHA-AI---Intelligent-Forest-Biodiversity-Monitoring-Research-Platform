# Reference firmware notes (ESP32 multi-sensor node)

This is a specification, not a maintained firmware project — adapt it to
whichever ESP32 toolchain you use.

## Reporting loop

```
loop every `report_interval_minutes`:
    read temperature_c, humidity_pct   from a BME280/DHT22
    read illuminance_lux               from an LDR / BH1750
    read soil_moisture_pct             (optional, capacitive probe)
    count motion_events since last report (PIR interrupt counter)
    read battery_volts                 (ADC on a divided battery line)

    POST https://<host>/api/v1/sensors/readings
    {
      "device_code": "<DEVICE_CODE>",
      "ingest_key": "<INGEST_KEY>",
      "readings": [{
        "recorded_at": "<ISO-8601 UTC timestamp>",
        "temperature_c": ..., "humidity_pct": ...,
        "illuminance_lux": ..., "soil_moisture_pct": ...,
        "sound_level_db": ..., "motion_events": ...,
        "battery_volts": ...
      }]
    }

    on failure: buffer the reading locally, retry with the next cycle
    (the endpoint rejects a reading older than 30 days or more than
    2 hours in the future — see backend/app/services/sensor_service.py)
```

Batch several buffered readings into one `readings` array (up to 500) after a
connectivity gap, instead of dropping them — the anomaly detector's baseline
depends on knowing which days actually had no data collection versus which
days simply were not reported yet.

## Power

Deep-sleep the MCU between reporting cycles; wake on a timer and on the PIR
interrupt for motion-triggered readings between scheduled reports. A 30-60
minute reporting interval is a reasonable default for a solar/battery node —
configured per-device via `report_interval_minutes` at registration, since
`app/services/sensor_service.py::device_health` uses it to decide when a node
counts as late or offline.

## Connectivity

Wi-Fi where available; for sites without it, an ESP32 + LoRa module reporting
to a gateway running the same HTTPS POST is the usual pattern — choose based
on the deployment site, not by assuming Wi-Fi will reach a forest interior.
