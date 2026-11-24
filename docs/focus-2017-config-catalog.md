# 2017 Focus configuration catalog

Scope: the captured Focus 2.0 GDI, not every 2017 Focus. Addresses below are hexadecimal CAN **request** addresses and diagnostic identifiers (DIDs), not FORScan display rows. This catalog records evidence; it is not a write allowlist.

## Named settings

| Setting                                | Module / DID       | Field                        | Evidence                                                                                                                                        | Still unknown                                           |
| -------------------------------------- | ------------------ | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| Key-in-ignition beep (operator's name) | IPC `720` / `DE11` | Third data byte, mask `0x80` | Operator identified the option; the [session](ford-focus-2017.md#changing-a-block) shows the bit cleared and restored, both writes acknowledged | Which state enables the beep; exact FORScan display row |

## Observed address inventory

Ranges are inclusive; gaps are intentional. Every DID below answered a read. Apart from the IPC field above, no named writable setting is established here. In particular, reading a VIN is not evidence of a configurable option.

| Module               | Bus | Request / reply | Readable DIDs                                      | Count |
| -------------------- | --- | --------------- | -------------------------------------------------- | ----: |
| BdyCM (body control) | HS  | `726` / `72E`   | `DE00–DE05`                                        |     6 |
| PCM (engine)         | HS  | `7E0` / `7E8`   | `DE00–DE01`                                        |     2 |
| APIM (SYNC)          | HS  | `7D0` / `7D8`   | `DE00–DE02`                                        |     3 |
| ABS                  | HS  | `760` / `768`   | `DE00` (VIN)                                       |     1 |
| RCM (restraints)     | HS  | `737` / `73F`   | `DE00` (VIN), `DE01–DE03`, `DE05`                  |     5 |
| PSCM (steering)      | HS  | `730` / `738`   | `DE00`                                             |     1 |
| FCDIM (display)      | MS  | `7A5` / `7AD`   | `DE00–DE03`                                        |     4 |
| ACM (audio)          | MS  | `727` / `72F`   | `DE00–DE07`                                        |     8 |
| IPC (cluster)        | MS  | `720` / `728`   | `DE00–DE0D`, `DE10–DE16`, `DE1A–DE1F`, `DE21–DE23` |    30 |
| GPSM (GPS)           | MS  | `701` / `709`   | `DE00–DE01`                                        |     2 |

Baseline: **62 readable blocks across 10 modules; one named field with an observed write and restore**. A block may contain many fields. See the [redacted capture inventory](data/focus-2017-asbuilt.txt) for individual lengths and refused identifiers. Do not derive `.abt` row numbers from DID offsets: the cluster backup has gaps in DID space.

### Mapping tracker

One row per readable module/DID pair. **Unmapped** means no field meaning is established; writability is unknown.

| Module | Request | DID    | Bytes | Mapping                                |
| ------ | ------- | ------ | ----: | -------------------------------------- |
| BdyCM  | `726`   | `DE00` |    50 | Unmapped                               |
| BdyCM  | `726`   | `DE01` |     4 | Unmapped                               |
| BdyCM  | `726`   | `DE02` |     2 | Unmapped                               |
| BdyCM  | `726`   | `DE03` |     2 | Unmapped                               |
| BdyCM  | `726`   | `DE04` |     1 | Unmapped                               |
| BdyCM  | `726`   | `DE05` |     1 | Unmapped                               |
| PCM    | `7E0`   | `DE00` |    52 | Unmapped                               |
| PCM    | `7E0`   | `DE01` |    52 | Unmapped                               |
| APIM   | `7D0`   | `DE00` |     8 | Unmapped                               |
| APIM   | `7D0`   | `DE01` |     6 | Unmapped                               |
| APIM   | `7D0`   | `DE02` |     5 | Unmapped                               |
| ABS    | `760`   | `DE00` |    17 | VIN (not a mapped setting)             |
| RCM    | `737`   | `DE00` |    17 | VIN (not a mapped setting)             |
| RCM    | `737`   | `DE01` |     8 | Unmapped                               |
| RCM    | `737`   | `DE02` |     2 | Unmapped                               |
| RCM    | `737`   | `DE03` |     2 | Unmapped                               |
| RCM    | `737`   | `DE05` |     1 | Unmapped                               |
| PSCM   | `730`   | `DE00` |     1 | Unmapped                               |
| FCDIM  | `7A5`   | `DE00` |     7 | Unmapped                               |
| FCDIM  | `7A5`   | `DE01` |     6 | Unmapped                               |
| FCDIM  | `7A5`   | `DE02` |     4 | Unmapped                               |
| FCDIM  | `7A5`   | `DE03` |     2 | Unmapped                               |
| ACM    | `727`   | `DE00` |     6 | Unmapped                               |
| ACM    | `727`   | `DE01` |     1 | Unmapped                               |
| ACM    | `727`   | `DE02` |     1 | Unmapped                               |
| ACM    | `727`   | `DE03` |     5 | Unmapped                               |
| ACM    | `727`   | `DE04` |    10 | Unmapped                               |
| ACM    | `727`   | `DE05` |    20 | Unmapped                               |
| ACM    | `727`   | `DE06` |    20 | Unmapped                               |
| ACM    | `727`   | `DE07` |    30 | Unmapped                               |
| IPC    | `720`   | `DE00` |     4 | Unmapped                               |
| IPC    | `720`   | `DE01` |    10 | Unmapped                               |
| IPC    | `720`   | `DE02` |     4 | Unmapped                               |
| IPC    | `720`   | `DE03` |     4 | Unmapped                               |
| IPC    | `720`   | `DE04` |     4 | Unmapped                               |
| IPC    | `720`   | `DE05` |     4 | Unmapped                               |
| IPC    | `720`   | `DE06` |     3 | Unmapped                               |
| IPC    | `720`   | `DE07` |     4 | Unmapped                               |
| IPC    | `720`   | `DE08` |     4 | Unmapped                               |
| IPC    | `720`   | `DE09` |     1 | Unmapped                               |
| IPC    | `720`   | `DE0A` |     4 | Unmapped                               |
| IPC    | `720`   | `DE0B` |    34 | Unmapped                               |
| IPC    | `720`   | `DE0C` |    22 | Unmapped                               |
| IPC    | `720`   | `DE0D` |    16 | Unmapped                               |
| IPC    | `720`   | `DE10` |     4 | Unmapped                               |
| IPC    | `720`   | `DE11` |     4 | Partially mapped: key-in-ignition beep |
| IPC    | `720`   | `DE12` |     4 | Unmapped                               |
| IPC    | `720`   | `DE13` |     4 | Unmapped                               |
| IPC    | `720`   | `DE14` |     4 | Unmapped                               |
| IPC    | `720`   | `DE15` |     4 | Unmapped                               |
| IPC    | `720`   | `DE16` |     4 | Unmapped                               |
| IPC    | `720`   | `DE1A` |     1 | Unmapped                               |
| IPC    | `720`   | `DE1B` |     4 | Unmapped                               |
| IPC    | `720`   | `DE1C` |     4 | Unmapped                               |
| IPC    | `720`   | `DE1D` |     4 | Unmapped                               |
| IPC    | `720`   | `DE1E` |     4 | Unmapped                               |
| IPC    | `720`   | `DE1F` |     1 | Unmapped                               |
| IPC    | `720`   | `DE21` |     4 | Unmapped                               |
| IPC    | `720`   | `DE22` |     4 | Unmapped                               |
| IPC    | `720`   | `DE23` |     4 | Unmapped                               |
| GPSM   | `701`   | `DE00` |     1 | Unmapped                               |
| GPSM   | `701`   | `DE01` |     7 | Unmapped                               |
