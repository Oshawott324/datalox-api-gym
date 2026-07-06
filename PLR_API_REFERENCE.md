# PyLabRobot (PLR) Instrument Module Overview

> 调研日期：2026-07-06 | PLR 版本：0.2.x

---

## 概览

PLR 共 **16 个仪器模块**（另有 1 个空模块 `plate_washing`），按层次分为：

- **P0 — 液体处理核心**：`liquid_handling`
- **P1 — 检测/传感**：`plate_reading`, `barcode_scanners`
- **P2 — 辅助液体**：`pumps`, `plate_washing`（空）
- **P3 — 称量/离散**：`scales`, `powder_dispensing`
- **P4 — 温控/震荡/倾斜**：`heating_shaking`, `shaking`, `temperature_controlling`, `tilting`
- **P5 — 离心/扩增**：`centrifuge`, `thermocycling`
- **P6 — 封装/存取**：`sealing`, `peeling`, `storage`
- **P7 — 机械臂**：`arms`

---

## 1. LiquidHandler (`liquid_handling`) ✅ 已覆盖 (28 场景)

**类**: `LiquidHandler` | **基类后端**: `LiquidHandlerBackend`

PLR 最核心模块，控制移液工作站的全部液体操作。

| 能力组 | 核心 API | 说明 |
|--------|---------|------|
| 单通道 | `pick_up_tips`, `drop_tips`, `discard_tips`, `return_tips`, `aspirate`, `dispense` | 8通道独立吸排液 |
| 96-head | `pick_up_tips96`, `drop_tips96`, `discard_tips96`, `aspirate96`, `dispense96` | 96通道并行操作 |
| iSWAP 机械臂 | `move_plate`, `move_lid`, `move_resource`, `pick_up_resource`, `drop_resource` | 板/盖/资源搬运 |
| 便捷方法 | `transfer`, `stamp` | 单次 transfer + 96→96 全板复制 |
| 查询 | `summary`, `get_mounted_tips`, `get_picked_up_resource` | 状态查询 |
| 库存 | `probe_tip_inventory`, `consolidate_tip_inventory` | Tip 探测与整理 |
| 状态追踪 | `set_tip_tracking(bool)`, `set_volume_tracking(bool)` | 自动追踪 tip/volume |

**典型 workflow**: `pick_up_tips → aspirate → dispense → discard_tips/return_tips`

---

## 2. PlateReader (`plate_reading`) ✅ 已覆盖 (4 场景)

**类**: `PlateReader` / `ImageReader` | **基类后端**: `PlateReaderBackend`

读板器/酶标仪，支持吸光度、荧光、发光三种模式。`ImageReader` 子类增加成像能力。

| 能力 | 核心 API |
|------|---------|
| 吸光度 | `read_absorbance(plate, wavelength)` |
| 荧光 | `read_fluorescence(plate, excitation, emission)` |
| 发光 | `read_luminescence(plate, integration_time)` |
| 门控 | `open()`, `close()` |
| 成像 (ImageReader) | `capture(well, mode, objective, exposure_time, ...)` |

---

## 3. Pump (`pumps`) ✅ 已覆盖 (4 场景)

**类**: `Pump` / `PumpArray` | **基类后端**: `PumpBackend`

蠕动泵，可校准体积或按时间/转数运行。`PumpArray` 支持多通道。

| 能力 | 核心 API |
|------|---------|
| 运行 | `run_for_duration(speed, duration)`, `run_revolutions(num)`, `run_continuously(speed)` |
| 校准 | `pump_volume(speed, volume)` — 需 `PumpCalibration` |
| 停止 | `halt()` |

---

## 4. Scale (`scales`) ✅ 已覆盖 (3 场景)

**类**: `Scale` | **基类后端**: `ScaleBackend`

分析天平，去皮/归零操作。

| 能力 | 核心 API |
|------|---------|
| 称重 | `get_weight()` |
| 去皮 | `tare()` |
| 归零 | `zero()` |

---

## 5. Centrifuge (`centrifuge`) ✅ 已覆盖 (3 场景)

**类**: `Centrifuge` / `Loader` | **基类后端**: `CentrifugeBackend`

离心机，门控 + 双桶定位 + g-force 离心。`Loader` 为自动上料器。

| 能力 | 核心 API |
|------|---------|
| 门控 | `open_door()`, `close_door()`, `lock_door()`, `unlock_door()` |
| 桶定位 | `go_to_bucket1()`, `go_to_bucket2()`, `lock_bucket()`, `unlock_bucket()` |
| 离心 | `spin(g, duration)`, `start_spin_cycle(g, duration)` |

---

## 6. HeaterShaker (`heating_shaking`) ✅ 已覆盖 (3 场景)

**类**: `HeaterShaker` | **基类后端**: `HeaterShakerBackend`（继承 `ShakerBackend` + `TemperatureControllerBackend`）

加热+震荡一体机，合并了 Shaker 和 TemperatureController 的全部能力。

| 能力 | 核心 API |
|------|---------|
| 温控 | `set_temperature(temp)`, `get_temperature()`, `deactivate()`, `wait_for_temperature()` |
| 震荡 | `shake(speed, duration)`, `stop_shaking()` |
| 锁板 | `lock_plate()`, `unlock_plate()` |

---

## 7. Thermocycler (`thermocycling`) ✅ 已覆盖 (3 场景)

**类**: `Thermocycler` | **基类后端**: `ThermocyclerBackend`

PCR 仪，分热盖 + 温块两个独立温控系统，支持完整 PCR 协议。

| 能力 | 核心 API |
|------|---------|
| 热盖 | `close_lid()`, `open_lid()`, `set_lid_temperature()`, `deactivate_lid()`, `get_lid_open()`, `wait_for_lid()` |
| 温块 | `set_block_temperature(temp, hold_time)`, `get_block_current_temperature()`, `deactivate_block()`, `wait_for_block()` |
| PCR 协议 | `run_protocol(protocol, block_max_volume)`, `run_pcr_profile(...)` — 自动执行多步/多循环 |
| 状态查询 | `is_profile_running()`, `get_current_cycle_index()`, `get_current_step_index()`, `get_total_cycle_count()` |

---

## 8. Arms (`arms`) ❌ 未覆盖

**类**: `ExperimentalSCARA` | **基类后端**: `SCARABackend` → `PreciseFlexBackend`

独立 6 轴机器人臂（PreciseFlex 系列），用于复杂空间操作。与 LiquidHandler 内置的 iSWAP 不同，Arms 具有完整的 Z 轴和姿态控制。

| 能力 | 核心 API |
|------|---------|
| 运动 | `home()`, `move_to(pos)`, `move_to_safe()`, `approach(pos, access)` |
| 夹持 | `pick_up_resource(pos, plate_width)`, `drop_resource(pos)`, `open_gripper(w)`, `close_gripper(w)` |
| 查询 | `get_cartesian_position()`, `get_joint_position()`, `is_gripper_closed()` |
| 特殊 | `freedrive_mode(axes)`, `end_freedrive_mode()`, `halt()` |

> **与 iSWAP 的区别**: iSWAP 是工作台内置板闸（2D 平移），Arms 是独立 6 轴机器人（3D 空间操作）。

---

## 9. Sealer (`sealing`) ❌ 未覆盖

**类**: `Sealer` | **基类后端**: `SealerBackend` | 后端实现: `A4SBackend`

热封膜机，对微孔板进行热封。

| 能力 | 核心 API |
|------|---------|
| 封膜 | `seal(temperature, duration)` |
| 门控 | `open()`, `close()` |
| 温控 | `set_temperature(temp)`, `get_temperature()` |
| A4S 扩展 | `set_heater(on/off)`, `get_status()`, `get_remaining_time()`, `system_reset()` |

---

## 10. Peeling (`peeling`) ❌ 未覆盖

**类**: `Peeler` | **基类后端**: `PeelerBackend` | 后端实现: `XPeelBackend`

揭膜/去膜机，用于去除微孔板上的封膜。

| 能力 | 核心 API |
|------|---------|
| 揭膜 | `peel(begin_location, fast, adhere_time)`, `seal_check()` |
| 传送 | `move_conveyor_in()`, `move_conveyor_out()` |
| 升降 | `move_elevator_up()`, `move_elevator_down()` |
| 胶带 | `advance_tape()`, `get_tape_remaining()` |
| 状态 | `get_status()`, `get_seal_sensor_status()`, `enable_plate_check()` |

---

## 11. Shaker (`shaking`) ❌ 未覆盖

**类**: `Shaker` | **基类后端**: `ShakerBackend`

**纯震荡器**（无加热功能），与 HeaterShaker 的区别在于不包含温度控制。

| 能力 | 核心 API |
|------|---------|
| 震荡 | `shake(speed, duration)`, `stop_shaking()` |
| 锁板 | `lock_plate()`, `unlock_plate()` |

---

## 12. TemperatureController (`temperature_controlling`) ❌ 未覆盖

**类**: `TemperatureController` | **基类后端**: `TemperatureControllerBackend`

**纯温控模块**（无震荡功能），与 HeaterShaker 的区别在于不含震荡。如 Opentrons Temperature Module。

| 能力 | 核心 API |
|------|---------|
| 温控 | `set_temperature(temp)`, `get_temperature()`, `deactivate()`, `wait_for_temperature()` |

---

## 13. Tilter (`tilting`) ❌ 未覆盖

**类**: `Tilter` / `HamiltonTiltModule` | **基类后端**: `TilterBackend`

倾斜模块，用于液体排液（如洗涤后倾斜排液），Hamilton STAR 可选配件。

| 能力 | 核心 API |
|------|---------|
| 倾斜 | `set_angle(absolute_angle)`, `tilt(relative_angle)` |
| 排液辅助 | `experimental_get_plate_drain_offsets(plate)`, `experimental_get_well_drain_offsets(wells)` |

---

## 14. Storage (`storage`) ❌ 未覆盖

**类**: `Incubator` | **基类后端**: `IncubatorBackend` | 后端实现: `CytomatBackend`, `LiconicBackend`, `SCILABackend`

恒温恒湿培养箱/板存储系统（Cytomat/Liconic/SCILA）。可同时存储多个 plate，提供温控、CO₂/O₂、湿度、震荡、条码扫描。

| 能力 | 核心 API |
|------|---------|
| 板存取 | `fetch_plate_to_loading_tray(plate)`, `take_in_plate(plate, site)` |
| 门控 | `open_door()`, `close_door()` |
| 环境 | `set_temperature()`, `get_temperature()`, `get_co2()`, `get_humidity()`, `get_o2()` |
| 震荡 | `set_shaking_frequency()`, `start_shaking()`, `stop_shaking()` |
| 转运 | `action_storage_to_exposed(site)`, `action_exposed_to_storage(site)`, `action_transfer_to_storage(site)` 等 10+ 种状态转移 |
| 状态 | `get_overview_register()`, `get_sensor_register()`, `get_error_register()`, `wait_for_task_completion()` |

---

## 15. PowderDispenser (`powder_dispensing`) ❌ 未覆盖

**类**: `PowderDispenser` | **基类后端**: `PowderDispenserBackend`

粉末分配器，将指定粉末按量分配到目标容器。

| 能力 | 核心 API |
|------|---------|
| 分配 | `dispense(resources, powders, amounts)` |

---

## 16. BarcodeScanner (`barcode_scanners`) ❌ 未覆盖

**类**: `BarcodeScanner` | **基类后端**: `BarcodeScannerBackend`

条码扫描器，读取微孔板/容器条码。

| 能力 | 核心 API |
|------|---------|
| 扫描 | `scan() → Barcode` |

---

## ⚠️ 17. Plate Washing (`plate_washing`)

**状态**: 空模块 — 无任何类或函数导出，洗板机尚未实现。

---

## 附录 A: 当前覆盖状态

| # | 模块 | 状态 | 场景数 |
|---|------|:---:|:---:|
| 1 | `liquid_handling` | ✅ | 28 |
| 2 | `plate_reading` | ✅ | 4 |
| 3 | `pumps` | ✅ | 4 |
| 4 | `scales` | ✅ | 3 |
| 5 | `centrifuge` | ✅ | 3 |
| 6 | `heating_shaking` | ✅ | 3 |
| 7 | `thermocycling` | ✅ | 3 |
| 8 | `arms` | ❌ | 0 |
| 9 | `sealing` | ❌ | 0 |
| 10 | `peeling` | ❌ | 0 |
| 11 | `shaking` | ❌ | 0 |
| 12 | `temperature_controlling` | ❌ | 0 |
| 13 | `tilting` | ❌ | 0 |
| 14 | `storage` | ❌ | 0 |
| 15 | `powder_dispensing` | ❌ | 0 |
| 16 | `barcode_scanners` | ❌ | 0 |
| — | `plate_washing` | ⚠️ 空模块 | — |
| **总计** | | **7/16** | **49** |

---

## 附录 B: 通用架构

所有 PLR 仪器遵循三层结构：

```
Instrument Class (用户层) → Backend ABC (抽象层) → Concrete Backend (硬件/dry-run)
```

构建 `*DryRunBackend` 时：继承对应的 `*Backend` 抽象类 → 实现所有 `[ABSTRACT]` 方法为 no-op（有状态仪器维护内部变量）→ 在 `state.py` 的 `create_*()` 工厂函数中实例化。
