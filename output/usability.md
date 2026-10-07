# Usability Improvements

Each improvement below is in the current code. For each: what was added, and why it helps a Campus Customs shopper or the business.

## Front end

### Four simple category filters with live counts
**Added:** The collection page now has five filter chips: Everything, T-shirts, Jackets, Hoodies, and Sweaters & Sweatshirts. Every catalogue item is mapped into one of these, and each chip shows how many pieces it holds (`frontend/src/App.tsx`, `getProductCategory` and `categoryCounts`). These replaced the old filters, which were too many and awkward.
**Why it helps:** Shoppers think in garment types, not database labels. Four clear choices with counts let them reach the right rack in one tap and never land on an empty filter. That means fewer bounces and quicker add-to-bag.

### Search that combines with filters, plus a clear-filters escape
**Added:** The search box matches every word against the name, type, description, tags, colors and ID, within the selected category. If nothing matches, "No pieces found." appears with a **Clear filters** button.
**Why it helps:** A search like "navy hoodie" finds what the shopper means, and a dead end is always one click from the full collection.

### Buttons that point to the next likely step
**Added:** One dark primary button per screen: "Shop the Halloween edit" on the home hero, "Browse the collection" in the promo pop-up, and "Add to bag" on product pages. Secondary actions such as "Our New Haven story" are styled as quieter text links. The hero product image links straight to its product page.
**Why it helps:** The eye goes to the action most shoppers want, which shortens the path from landing to product to bag.

### Size buttons that show stock
**Added:** On a product page, sold-out sizes are greyed out and disabled. Hovering a size shows the units in stock, and screen readers hear the same. "Add to bag" is disabled when no size is in stock.
**Why it helps:** Shoppers can't pick a size that isn't there, and the business avoids orders it can't fill.

### Chat results open the same product pages
**Added:** When the assistant answers a category question ("what hoodies do you have?"), matching product cards appear in the chat. Each card opens the same detail page as the catalogue.
**Why it helps:** Browsing in chat flows straight into buying, without making the shopper search again.

## Back end (agent)

### Search ranking that favors names over passing mentions
**Added:** `search_shop_catalogue` scores product ID and name matches above tag matches, and tag matches above words that only appear in a description. It returns at most 4 results (`backend/tools.py`).
**Why it helps:** The agent sees the right product first, so answers are more accurate. The small result set keeps prompts short, which makes them cheaper and faster.

### Product cards rebuilt from the database, never from model text
**Added:** The agent returns only product IDs. FastAPI checks each ID in SQLite, drops any it can't find, and builds the card's name, price, image and stock from the database (`backend/main.py`).
**Why it helps:** Shoppers never see an invented product, price or stock count. That protects trust and avoids pricing mistakes.

### Loop limits and an audit trail
**Added:** Each chat message is capped at 6 model requests, 8 tool calls and 2,000 output tokens. Every run is logged to `output/audit_trail.json` (`backend/agent.py`).
**Why it helps:** Cost per message stays bounded and runaway loops stop cleanly. The business can see which tools ran and why each answer stopped.
