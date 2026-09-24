"""
A realistic Kenyan supermarket catalogue for demos and training.

Loaded by `flask seed-demo`. Prices are typical shelf prices in KES; costs
assume a normal retail margin. Barcodes are valid EAN-13 numbers in the 616
(Kenya) range, generated from the product's position so they never change.
"""

# (name, cost, price, opening stock, low-stock level, unit)
CATALOG = {
    "Beverages": [
        ("Coca-Cola 500ml", 55, 80, 96, 24, "pc"),
        ("Coca-Cola 2L", 150, 200, 36, 8, "pc"),
        ("Fanta Orange 500ml", 55, 80, 72, 24, "pc"),
        ("Sprite 500ml", 55, 80, 72, 24, "pc"),
        ("Stoney Tangawizi 500ml", 55, 80, 48, 12, "pc"),
        ("Keringet Water 500ml", 30, 50, 120, 24, "pc"),
        ("Dasani Water 1L", 50, 70, 60, 12, "pc"),
        ("Keringet Water 5L", 190, 260, 20, 5, "pc"),
        ("Minute Maid Mango 400ml", 60, 90, 40, 10, "pc"),
        ("Pick N Peel Orange Juice 1L", 210, 280, 18, 5, "pc"),
        ("Afia Mango Juice 500ml", 55, 85, 36, 10, "pc"),
        ("Red Bull 250ml", 170, 230, 30, 6, "pc"),
        ("Monster Energy 500ml", 190, 250, 24, 6, "pc"),
        ("Ribena Blackcurrant 1L", 360, 450, 12, 3, "pc"),
        ("Pepsi 1.25L", 100, 140, 36, 8, "pc"),
    ],
    "Dairy & Eggs": [
        ("Brookside Milk 500ml", 50, 65, 80, 20, "pc"),
        ("Brookside Milk 1L", 100, 130, 40, 10, "pc"),
        ("Tuzo Long Life Milk 500ml", 55, 70, 60, 12, "pc"),
        ("KCC Mala 500ml", 60, 80, 30, 8, "pc"),
        ("Daima Yoghurt Strawberry 500ml", 110, 150, 24, 6, "pc"),
        ("Brookside Yoghurt Vanilla 250ml", 55, 75, 30, 8, "pc"),
        ("Blue Band 500g", 180, 235, 36, 8, "pc"),
        ("Brookside Butter 250g", 280, 360, 12, 4, "pc"),
        ("Eggs Tray (30)", 390, 480, 20, 5, "tray"),
        ("Eggs Half Dozen", 85, 110, 30, 8, "pack"),
        ("Cheddar Cheese 200g", 380, 490, 10, 3, "pc"),
    ],
    "Bakery": [
        ("Supa Loaf White Bread 400g", 52, 65, 40, 10, "pc"),
        ("Festive Brown Bread 400g", 55, 70, 30, 8, "pc"),
        ("Superloaf White Bread 800g", 100, 125, 20, 6, "pc"),
        ("Dinner Rolls (6)", 70, 100, 15, 4, "pack"),
        ("Queen Cakes (6)", 90, 130, 12, 4, "pack"),
        ("Mandazi (5)", 30, 50, 20, 5, "pack"),
        ("Chapati (5)", 60, 90, 15, 5, "pack"),
    ],
    "Rice & Grains": [
        ("Pishori Rice 1kg", 170, 220, 40, 10, "pc"),
        ("Pishori Rice 2kg", 330, 420, 25, 6, "pc"),
        ("Daawat Basmati Rice 1kg", 260, 330, 20, 5, "pc"),
        ("Sunrice Long Grain 1kg", 150, 190, 30, 8, "pc"),
        ("Green Grams (Ndengu) 1kg", 180, 240, 20, 5, "pc"),
        ("Rose Coco Beans 1kg", 170, 220, 25, 6, "pc"),
        ("Lentils (Kamande) 1kg", 190, 250, 15, 4, "pc"),
        ("Popcorn Maize 500g", 70, 100, 15, 4, "pc"),
    ],
    "Flour & Baking": [
        ("Jogoo Maize Flour 2kg", 150, 185, 60, 15, "pc"),
        ("Soko Maize Flour 2kg", 140, 175, 50, 12, "pc"),
        ("Pembe Maize Flour 2kg", 145, 180, 40, 10, "pc"),
        ("Ajab Home Baking Flour 2kg", 160, 205, 40, 10, "pc"),
        ("Exe All Purpose Flour 2kg", 165, 210, 35, 8, "pc"),
        ("Dola Wheat Flour 1kg", 85, 110, 30, 8, "pc"),
        ("Mama Millet Porridge Flour 1kg", 120, 160, 20, 5, "pc"),
        ("Baking Powder 100g", 60, 85, 20, 5, "pc"),
        ("Instant Yeast 11g", 25, 40, 40, 10, "pc"),
    ],
    "Cooking Oil & Fats": [
        ("Fresh Fri Cooking Oil 1L", 300, 380, 36, 8, "pc"),
        ("Fresh Fri Cooking Oil 3L", 850, 1050, 15, 4, "pc"),
        ("Rina Vegetable Oil 1L", 280, 350, 30, 8, "pc"),
        ("Elianto Corn Oil 1L", 380, 470, 18, 5, "pc"),
        ("Kimbo Cooking Fat 500g", 190, 240, 30, 8, "pc"),
        ("Kasuku Cooking Fat 1kg", 350, 440, 15, 4, "pc"),
        ("Golden Fry Oil 5L", 1350, 1650, 8, 2, "pc"),
    ],
    "Sugar & Sweeteners": [
        ("Mumias Sugar 1kg", 150, 185, 60, 15, "pc"),
        ("Mumias Sugar 2kg", 295, 360, 30, 8, "pc"),
        ("Kabras Sugar 1kg", 148, 180, 40, 10, "pc"),
        ("Brown Sugar 1kg", 160, 200, 20, 5, "pc"),
        ("Honey 500g", 380, 480, 10, 3, "pc"),
    ],
    "Tea & Coffee": [
        ("Ketepa Pride Tea Leaves 250g", 130, 170, 40, 10, "pc"),
        ("Kericho Gold Tea Bags (50)", 170, 220, 30, 8, "pack"),
        ("Fahari Tea Leaves 500g", 220, 280, 20, 5, "pc"),
        ("Nescafe Classic 50g", 280, 360, 20, 5, "pc"),
        ("Dormans Ground Coffee 250g", 420, 530, 10, 3, "pc"),
        ("Milo Tin 400g", 520, 650, 12, 3, "pc"),
        ("Drinking Chocolate 200g", 230, 300, 12, 3, "pc"),
    ],
    "Snacks & Confectionery": [
        ("Tropical Heat Crisps 50g", 40, 60, 60, 15, "pc"),
        ("Pringles Original 165g", 330, 420, 18, 5, "pc"),
        ("Nuvita Biscuits 200g", 55, 80, 50, 12, "pc"),
        ("Marie Biscuits 250g", 60, 85, 40, 10, "pc"),
        ("Digestive Biscuits 400g", 180, 240, 20, 5, "pc"),
        ("Cadbury Dairy Milk 80g", 170, 230, 24, 6, "pc"),
        ("KitKat 4 Finger", 90, 120, 30, 8, "pc"),
        ("Orbit Chewing Gum", 40, 60, 50, 12, "pc"),
        ("Big G Bubble Gum (10)", 10, 20, 100, 20, "pack"),
        ("Roasted Peanuts 100g", 45, 70, 40, 10, "pc"),
        ("Cashew Nuts 100g", 200, 270, 15, 4, "pc"),
        ("Tropical Heat Cassava Crisps 100g", 80, 110, 25, 6, "pc"),
    ],
    "Canned & Packaged": [
        ("Heinz Baked Beans 415g", 150, 195, 30, 8, "pc"),
        ("Tomato Paste Gino 70g", 25, 40, 60, 15, "pc"),
        ("Zesta Tomato Sauce 400g", 150, 195, 20, 5, "pc"),
        ("Sardines Ocean Fresh 155g", 90, 125, 30, 8, "pc"),
        ("Tuna Chunks in Oil 185g", 230, 290, 20, 5, "pc"),
        ("Coconut Milk Tin 400ml", 130, 170, 20, 5, "pc"),
        ("Indomie Noodles Chicken 70g", 30, 45, 120, 30, "pc"),
        ("Santa Lucia Spaghetti 400g", 100, 135, 40, 10, "pc"),
        ("Macaroni 400g", 95, 130, 30, 8, "pc"),
        ("Royco Mchuzi Mix 200g", 110, 145, 30, 8, "pc"),
    ],
    "Spices & Condiments": [
        ("Kensalt Table Salt 1kg", 35, 50, 50, 12, "pc"),
        ("Tropical Heat Pilau Masala 50g", 60, 85, 30, 8, "pc"),
        ("Tropical Heat Curry Powder 50g", 55, 80, 25, 6, "pc"),
        ("Black Pepper 50g", 90, 125, 15, 4, "pc"),
        ("Royco Cubes Beef (12)", 45, 65, 40, 10, "pack"),
        ("Tomato Ketchup 400g", 170, 220, 20, 5, "pc"),
        ("Chilli Sauce 400g", 180, 230, 15, 4, "pc"),
        ("Mayonnaise 400g", 290, 370, 12, 3, "pc"),
        ("White Vinegar 750ml", 90, 120, 15, 4, "pc"),
    ],
    "Breakfast": [
        ("Weetabix 430g", 380, 470, 15, 4, "pc"),
        ("Kellogg's Corn Flakes 500g", 480, 590, 12, 3, "pc"),
        ("Quaker Oats 500g", 280, 350, 15, 4, "pc"),
        ("Peanut Butter 400g", 290, 370, 15, 4, "pc"),
        ("Strawberry Jam 450g", 250, 320, 15, 4, "pc"),
    ],
    "Fresh Produce": [
        ("Tomatoes", 90, 120, 40, 10, "kg"),
        ("Onions (Red)", 100, 140, 40, 10, "kg"),
        ("Potatoes", 70, 100, 60, 15, "kg"),
        ("Sukuma Wiki (bunch)", 15, 25, 40, 10, "bunch"),
        ("Cabbage", 50, 80, 20, 5, "pc"),
        ("Carrots", 80, 110, 20, 5, "kg"),
        ("Bananas (ripe)", 90, 130, 25, 6, "kg"),
        ("Oranges", 120, 160, 20, 5, "kg"),
        ("Avocado", 20, 35, 40, 10, "pc"),
        ("Garlic 250g", 70, 100, 15, 4, "pc"),
    ],
    "Personal Care": [
        ("Colgate Toothpaste 140g", 170, 220, 30, 8, "pc"),
        ("Close Up Toothpaste 100g", 120, 160, 25, 6, "pc"),
        ("Toothbrush Medium", 40, 70, 40, 10, "pc"),
        ("Geisha Bathing Soap 225g", 90, 120, 40, 10, "pc"),
        ("Dettol Soap 175g", 130, 170, 30, 8, "pc"),
        ("Nice & Lovely Lotion 400ml", 250, 320, 15, 4, "pc"),
        ("Vaseline Petroleum Jelly 250ml", 240, 310, 15, 4, "pc"),
        ("Always Pads Maxi (8)", 110, 150, 30, 8, "pack"),
        ("Rexona Roll-On 50ml", 220, 290, 15, 4, "pc"),
        ("Gillette Blue II Razor (5)", 150, 200, 20, 5, "pack"),
        ("Softcare Tissue 10 Rolls", 380, 480, 20, 5, "pack"),
        ("Head & Shoulders Shampoo 200ml", 380, 480, 10, 3, "pc"),
    ],
    "Household & Cleaning": [
        ("Omo Washing Powder 1kg", 320, 400, 25, 6, "pc"),
        ("Ariel Washing Powder 500g", 180, 230, 25, 6, "pc"),
        ("Sunlight Bar Soap 800g", 180, 230, 30, 8, "pc"),
        ("Menengai Bar Soap 1kg", 170, 220, 25, 6, "pc"),
        ("Jik Bleach 750ml", 130, 170, 20, 5, "pc"),
        ("Harpic Toilet Cleaner 500ml", 230, 290, 15, 4, "pc"),
        ("Dishwashing Liquid 500ml", 120, 165, 25, 6, "pc"),
        ("Doom Insect Spray 300ml", 350, 440, 12, 3, "pc"),
        ("Steel Wool (4)", 40, 60, 30, 8, "pack"),
        ("Matchbox (10)", 30, 50, 40, 10, "pack"),
        ("Candles (6)", 70, 100, 20, 5, "pack"),
        ("Garbage Bags (10)", 90, 130, 20, 5, "pack"),
        ("Kiwi Shoe Polish Black", 110, 150, 15, 4, "pc"),
    ],
    "Baby Care": [
        ("Pampers Diapers Size 3 (30)", 1150, 1400, 10, 3, "pack"),
        ("Huggies Wipes (56)", 220, 290, 15, 4, "pack"),
        ("Johnson's Baby Oil 200ml", 330, 420, 10, 3, "pc"),
        ("Cerelac Wheat 400g", 520, 650, 8, 2, "pc"),
        ("NAN 1 Infant Formula 400g", 1650, 1950, 6, 2, "pc"),
    ],
}

# First letters of the aisle, used for readable SKUs such as BEV-0001.
PREFIX = {
    "Beverages": "BEV",
    "Dairy & Eggs": "DRY",
    "Bakery": "BKY",
    "Rice & Grains": "RIC",
    "Flour & Baking": "FLR",
    "Cooking Oil & Fats": "OIL",
    "Sugar & Sweeteners": "SUG",
    "Tea & Coffee": "TEA",
    "Snacks & Confectionery": "SNK",
    "Canned & Packaged": "CAN",
    "Spices & Condiments": "SPC",
    "Breakfast": "BRK",
    "Fresh Produce": "FRS",
    "Personal Care": "PER",
    "Household & Cleaning": "HSH",
    "Baby Care": "BBY",
}

# Loose produce is weighed or counted at the till, so it has no barcode.
NO_BARCODE = {"Fresh Produce"}


def ean13(body12):
    """Append the EAN-13 check digit to a 12-digit string."""
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body12))
    return body12 + str((10 - total % 10) % 10)


def catalog_rows():
    """Yield (category, sku, barcode, name, cost, price, stock, threshold, unit)."""
    number = 0
    for category, items in CATALOG.items():
        for index, (name, cost, price, stock, threshold, unit) in enumerate(items, start=1):
            number += 1
            sku = "%s-%04d" % (PREFIX[category], index)
            barcode = None if category in NO_BARCODE else ean13("6168%08d" % (10000 + number))
            yield category, sku, barcode, name, cost, price, stock, threshold, unit
