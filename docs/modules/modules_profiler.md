# modules_profiler
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Profiler module.

## Key Classes
- **ProfilerState** - Holds thread tags, CPU times and inference durations.
- **Profiler** - Background profiler thread.

## Key Functions
- **register_thread(tag, state)** - Register current thread with a tag for profiling.
- **log_inference(tag, duration, state)** - Record a YOLOv8 inference duration.
- **profile_predict(model, tag)** - Wrap YOLOv8 ``predict`` and log inference duration.
- **_calc_cpu_percent(state, tid, cpu_time, now)** -
- **_collect_stats(state)** - Return stats for registered threads.
- **log_resource_usage(tag)** - Immediately log resource usage for the given tag.
- **start_profiler(cfg)** - Start the background profiler if enabled in config.
- **stop_profiler()** - Stop the background profiler.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- loguru
- psutil
- threading
- time
- typing
