from typing import Literal

from pydantic import BaseModel, Field


class ChatHistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1200)
    history: list[ChatHistoryTurn] = Field(default_factory=list, max_length=8)
    page_context_product_id: str | None = Field(default=None, max_length=120)


class ChatProductMatch(BaseModel):
    product_id: str = Field(min_length=1, max_length=120)
    match_reason: str = Field(min_length=1, max_length=240)


class ChatReply(BaseModel):
    reply: str = Field(min_length=1, max_length=1600)
    product_matches: list[ChatProductMatch] = Field(default_factory=list, max_length=3)


class ProductSizeStock(BaseModel):
    size: str
    quantity: int = Field(ge=0)
    in_stock: bool


class ProductCard(BaseModel):
    product_id: str
    name: str
    garment_type: str
    description: str
    price: float = Field(ge=0)
    image_url: str
    colors: list[str] = Field(default_factory=list)
    sizes: list[ProductSizeStock] = Field(default_factory=list)


class ProductDetailsLookup(BaseModel):
    product_id: str
    name: str
    garment_type: str
    description: str
    colors: list[str] = Field(default_factory=list)


class ProductPriceLookup(BaseModel):
    product_id: str
    name: str
    price: float = Field(ge=0)
    currency: str = "USD"


class ProductStockLookup(BaseModel):
    product_id: str
    name: str
    requested_size: str | None = None
    size_records: list[ProductSizeStock] = Field(default_factory=list)
    availability: Literal["in_stock", "out_of_stock", "unknown"]
    message: str


class ChatResponse(BaseModel):
    reply: str
    products: list[ProductCard] = Field(default_factory=list, max_length=3)


class ChatHistoryEntry(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1600)
    created_at: str
    products: list[ProductCard] = Field(default_factory=list, max_length=3)


class ChatHistoryResponse(BaseModel):
    authenticated: bool
    messages: list[ChatHistoryEntry] = Field(default_factory=list, max_length=60)