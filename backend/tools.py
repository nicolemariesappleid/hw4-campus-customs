import json
import sqlite3
from contextlib import closing
from pathlib import Path

try:
    from .models import (
        ProductCard,
        ProductDetailsLookup,
        ProductPriceLookup,
        ProductSizeStock,
        ProductStockLookup,
    )
except ImportError:
    from models import (
        ProductCard,
        ProductDetailsLookup,
        ProductPriceLookup,
        ProductSizeStock,
        ProductStockLookup,
    )


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _parse_colors(value: str | None) -> list[str]:
    try:
        colors = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(colors, list):
        return []
    return [str(color) for color in colors]


def _size_order() -> str:
    return (
        "CASE size WHEN 'XXS' THEN 1 WHEN 'XS' THEN 2 WHEN 'S' THEN 3 "
        "WHEN 'M' THEN 4 WHEN 'L' THEN 5 WHEN 'XL' THEN 6 "
        "WHEN 'XXL' THEN 7 WHEN 'XXXL' THEN 8 ELSE 9 END, size"
    )


def _get_product(connection: sqlite3.Connection, product_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT product_id, name, garment_type, description, colors, price, image_file_path "
        "FROM catalogue WHERE product_id = ?",
        (product_id,),
    ).fetchone()


def search_catalogue(
    database_path: Path,
    query: str,
    garment_type: str | None = None,
    max_results: int = 4,
) -> list[ProductCard]:
    """Search only the shop catalogue and return factual product and size data."""
    terms = [term for term in query.casefold().split() if len(term) > 1][:8]
    if not terms:
        return []

    connection = _connect(database_path)
    try:
        rows = connection.execute(
            "SELECT * FROM catalogue ORDER BY name COLLATE NOCASE"
        ).fetchall()
        matches: list[tuple[int, sqlite3.Row]] = []
        for row in rows:
            name = row["name"].casefold()
            product_id_text = row["product_id"].replace("-", " ").casefold()
            tags = row["search_tags"].casefold()
            secondary_text = " ".join(
                (row["garment_type"], row["description"], row["colors"])
            ).casefold()
            if garment_type and garment_type.casefold() not in row["garment_type"].casefold():
                continue
            score = sum(
                name.count(term) * 5
                + product_id_text.count(term) * 7
                + tags.count(term) * 3
                + secondary_text.count(term)
                for term in terms
            )
            if score:
                matches.append((score, row))

        matches.sort(key=lambda match: (-match[0], match[1]["name"].casefold()))
        products = []
        for _, row in matches[: max(1, min(max_results, 5))]:
            size_rows = connection.execute(
                f"SELECT size, quantity FROM inventory WHERE product_id = ? "
                f"ORDER BY {_size_order()}",
                (row["product_id"],),
            ).fetchall()
            products.append(
                ProductCard(
                    product_id=row["product_id"],
                    name=row["name"],
                    garment_type=row["garment_type"],
                    description=row["description"],
                    price=row["price"],
                    image_url=f"/images/{Path(row['image_file_path']).name}",
                    colors=_parse_colors(row["colors"]),
                    sizes=[
                        ProductSizeStock(
                            size=size["size"],
                            quantity=size["quantity"],
                            in_stock=size["quantity"] > 0,
                        )
                        for size in size_rows
                    ],
                )
            )
        return products
    finally:
        connection.close()


def get_product_details(database_path: Path, product_id: str) -> ProductDetailsLookup | None:
    """Return exact product name, garment type, description, and colors by product ID."""
    with closing(_connect(database_path)) as connection:
        row = _get_product(connection, product_id)
        if row is None:
            return None
        return ProductDetailsLookup(
            product_id=row["product_id"],
            name=row["name"],
            garment_type=row["garment_type"],
            description=row["description"],
            colors=_parse_colors(row["colors"]),
        )


def get_product_price(database_path: Path, product_id: str) -> ProductPriceLookup | None:
    """Return the current catalogue price by exact product ID; never estimate or infer it."""
    with closing(_connect(database_path)) as connection:
        row = _get_product(connection, product_id)
        if row is None:
            return None
        return ProductPriceLookup(
            product_id=row["product_id"],
            name=row["name"],
            price=row["price"],
        )


def get_product_stock(
    database_path: Path,
    product_id: str,
    size: str | None = None,
) -> ProductStockLookup | None:
    """Return stock for one requested size or all recorded sizes by exact product ID."""
    normalized_size = size.strip().upper() if size else None
    with closing(_connect(database_path)) as connection:
        product = _get_product(connection, product_id)
        if product is None:
            return None

        if normalized_size:
            rows = connection.execute(
                "SELECT size, quantity FROM inventory "
                "WHERE product_id = ? AND UPPER(size) = ?",
                (product_id, normalized_size),
            ).fetchall()
        else:
            rows = connection.execute(
                f"SELECT size, quantity FROM inventory WHERE product_id = ? "
                f"ORDER BY {_size_order()}",
                (product_id,),
            ).fetchall()

        records = [
            ProductSizeStock(
                size=row["size"],
                quantity=row["quantity"],
                in_stock=row["quantity"] > 0,
            )
            for row in rows
        ]
        if not records:
            availability = "unknown"
            message = (
                f"No inventory record exists for size {normalized_size} of {product['name']}. "
                "Availability is unknown."
                if normalized_size
                else f"No size inventory records exist for {product['name']}. Availability is unknown."
            )
        elif normalized_size and records[0].quantity == 0:
            availability = "out_of_stock"
            message = f"{product['name']} is out of stock in size {records[0].size}."
        elif normalized_size:
            availability = "in_stock"
            message = (
                f"{product['name']} has {records[0].quantity} units in stock "
                f"in size {records[0].size}."
            )
        elif any(record.quantity > 0 for record in records):
            availability = "in_stock"
            message = f"Current recorded size-by-size stock for {product['name']}."
        else:
            availability = "out_of_stock"
            message = f"{product['name']} is out of stock in all recorded sizes."

        return ProductStockLookup(
            product_id=product["product_id"],
            name=product["name"],
            requested_size=normalized_size,
            size_records=records,
            availability=availability,
            message=message,
        )