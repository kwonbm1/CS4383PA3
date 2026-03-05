import argparse
import os
import zmq

from fbschemas.grocery.fb import AnalyticsEvent


# PA2: Config via env for K8s multi-cluster (NodePort). Defaults = PA1 multi-VM.
ORDERING_HOST = os.environ.get("ORDERING_HOST", "172.16.5.77")
ORDERING_ZMQ_PORT = os.environ.get("ORDERING_ZMQ_PORT", "5557")
DEFAULT_ZMQ_SUB_ADDR = f"tcp://{ORDERING_HOST}:{ORDERING_ZMQ_PORT}"


class AnalyticsCollector:
    """Collects analytics events and computes running statistics."""

    def __init__(self):
        self.total_orders = 0
        self.successful_orders = 0
        self.failed_orders = 0
        self.total_latency_ms = 0.0
        self.min_latency_ms = float("inf")
        self.max_latency_ms = 0.0

        # Per-type stats
        self.stats_by_type: dict[str, dict] = {}

    def record(self, event_type: str, latency_ms: float, success: bool):
        self.total_orders += 1
        self.total_latency_ms += latency_ms

        if latency_ms < self.min_latency_ms:
            self.min_latency_ms = latency_ms
        if latency_ms > self.max_latency_ms:
            self.max_latency_ms = latency_ms

        if success:
            self.successful_orders += 1
        else:
            self.failed_orders += 1

        # Per-type tracking
        if event_type not in self.stats_by_type:
            self.stats_by_type[event_type] = {
                "count": 0, "success": 0, "failed": 0,
                "total_latency": 0.0,
            }
        s = self.stats_by_type[event_type]
        s["count"] += 1
        s["total_latency"] += latency_ms
        if success:
            s["success"] += 1
        else:
            s["failed"] += 1

    def avg_latency(self) -> float:
        if self.total_orders == 0:
            return 0.0
        return self.total_latency_ms / self.total_orders

    def dump(self):
        print("=" * 60, flush=True)
        print("  ANALYTICS SUMMARY", flush=True)
        print("=" * 60, flush=True)
        print(f"  Total orders processed: {self.total_orders}", flush=True)
        print(f"  Successful:             {self.successful_orders}", flush=True)
        print(f"  Failed:                 {self.failed_orders}", flush=True)
        if self.total_orders > 0:
            print(f"  Avg latency:            {self.avg_latency():.1f} ms",
                  flush=True)
            min_val = self.min_latency_ms if self.min_latency_ms != float("inf") else 0
            print(f"  Min latency:            {min_val:.1f} ms", flush=True)
            print(f"  Max latency:            {self.max_latency_ms:.1f} ms",
                  flush=True)

        for etype, s in self.stats_by_type.items():
            avg = s["total_latency"] / s["count"] if s["count"] > 0 else 0
            print(f"  [{etype}] count={s['count']} "
                  f"ok={s['success']} fail={s['failed']} "
                  f"avg_latency={avg:.1f}ms", flush=True)
        print("=" * 60, flush=True)


def main(zmq_addr: str):
    collector = AnalyticsCollector()

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.connect(zmq_addr)
    sub.setsockopt(zmq.SUBSCRIBE, b"ANALYTICS")

    print(f"[analytics_service] subscribed to {zmq_addr}", flush=True)
    print("[analytics_service] waiting for events...", flush=True)

    while True:
        topic, payload = sub.recv_multipart()

        evt = AnalyticsEvent.AnalyticsEvent.GetRootAsAnalyticsEvent(payload, 0)
        event_id = evt.EventId().decode() if evt.EventId() else "?"
        source = evt.Source().decode() if evt.Source() else "?"
        event_type = evt.EventType().decode() if evt.EventType() else "?"
        timestamp_ms = evt.TimestampMs()
        latency_ms = evt.LatencyMs()
        success = evt.Success()

        print(f"[analytics_service] event: id={event_id[:8]}... "
              f"src={source} type={event_type} "
              f"latency={latency_ms:.1f}ms success={success}",
              flush=True)

        collector.record(event_type, latency_ms, success)
        collector.dump()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analytics Service")
    parser.add_argument(
        "--zmq-addr", default=DEFAULT_ZMQ_SUB_ADDR,
        help=f"ZMQ SUB address (default: {DEFAULT_ZMQ_SUB_ADDR})",
    )
    args = parser.parse_args()
    main(zmq_addr=args.zmq_addr)
