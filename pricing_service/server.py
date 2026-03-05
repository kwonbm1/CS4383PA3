from concurrent import futures
import os
import grpc

from proto import common_pb2 as pb2
from proto import inventory_pricing_pb2 as pricing_pb2
from proto import inventory_pricing_pb2_grpc as pricing_grpc


# ----------------------------
# Price table (per unit)
# ----------------------------
ITEM_PRICES = {
    # Bread aisle
    "bagels":       3.99,
    "bread":        2.49,
    "waffles":      4.29,
    "tortillas":    3.49,
    "buns":         2.99,
    # Dairy aisle
    "milk":         4.59,
    "eggs":         3.99,
    "cheese":       5.49,
    "yogurt":       1.29,
    "butter":       4.99,
    # Meat aisle
    "chicken":      8.99,
    "beef":        11.99,
    "pork":         7.49,
    "turkey":       9.49,
    "fish":        12.99,
    # Produce aisle
    "tomatoes":     2.99,
    "onions":       1.49,
    "apples":       1.99,
    "oranges":      2.49,
    "lettuce":      1.79,
    # Party aisle
    "soda":         1.99,
    "paper_plates": 3.49,
    "napkins":      2.49,
    "chips":        4.29,
    "cups":         2.99,
}


# ----------------------------
# Service
# ----------------------------
class PricingServiceImpl(pricing_grpc.PricingServiceServicer):
    def GetTotalPrice(self, request: pricing_pb2.PriceRequest, context):
        total = 0.0
        for item in request.items:
            unit_price = ITEM_PRICES.get(item.item, 0.0)
            total += unit_price * item.qty

        total = round(total, 2)

        print(f"[pricing_service] calculated total=${total:.2f} for "
              f"{len(request.items)} line items", flush=True)

        return pricing_pb2.PriceResponse(
            code=pb2.OK,
            message=f"Total: ${total:.2f}",
            total_price=total,
        )


def serve(grpc_host="0.0.0.0", grpc_port=50052):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pricing_grpc.add_PricingServiceServicer_to_server(
        PricingServiceImpl(), server
    )
    server.add_insecure_port(f"{grpc_host}:{grpc_port}")
    server.start()
    print(f"[pricing_service] gRPC listening on {grpc_host}:{grpc_port}",
          flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    port = int(os.environ.get("PRICING_GRPC_PORT", "50052"))
    serve(grpc_host="0.0.0.0", grpc_port=port)
