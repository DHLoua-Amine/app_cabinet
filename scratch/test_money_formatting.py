import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'c:\Users\amin\Desktop\zarai1_pyside\core')
sys.path.insert(0, r'c:\Users\amin\Desktop\zarai1_pyside')

from core.contract_templates import format_money_words_and_numbers, build_multi_party_contract_text

# Test 1: Helper function
print("--- Test 1: Helper function tests ---")
t1 = format_money_words_and_numbers("", "5000")
print("Inputs ('', '5000') =>", t1)
assert "خمسة آلاف" in t1 and "(5000 د.ت)" in t1

t2 = format_money_words_and_numbers("5000", "5000")
print("Inputs ('5000', '5000') =>", t2)
assert "خمسة آلاف" in t2 and "(5000 د.ت)" in t2

t3 = format_money_words_and_numbers("خمسة آلاف", "5000")
print("Inputs ('خمسة آلاف', '5000') =>", t3)
assert "خمسة آلاف" in t3 and "(5000 د.ت)" in t3

t4 = format_money_words_and_numbers("", "1250.500")
print("Inputs ('', '1250.500') =>", t4)
assert "ألف ومائتان وخمسون" in t4 and "(1250.500 د.ت)" in t4

# Test 2: Full Contract Text Generation
print("\n--- Test 2: Full Contract Generation ---")
party1 = [{"full_name": "على بن أحمد Zarai", "cin_number": "01234567"}]
party2 = [{"full_name": "مريم بنت صالح", "cin_number": "07654321"}]

# Sale Contract
sale_text = build_multi_party_contract_text(
    contract_type="عقد بيع",
    party1_list=party1,
    party2_list=party2,
    property_desc="قطع أرض فلاحية بـ الكاف",
    price_num="5000",
    price_words=""
)
print("SALE CONTRACT PRICE CLAUSE:")
print(sale_text)
assert "خمسة آلاف دينار (5000 د.ت)" in sale_text
print("  => PASS: Found 'خمسة آلاف دينار (5000 د.ت)' in Sale Contract!")

# Rent Contract
keraa_text = build_multi_party_contract_text(
    contract_type="عقد كراء توثيقي",
    party1_list=party1,
    party2_list=party2,
    property_desc="محل تجاري بـ فوشانة",
    price_num="450",
    price_words=""
)
print("\nRENT CONTRACT PRICE CLAUSE:")
print(keraa_text)
assert "أربعمائة وخمسون دينار (450 د.ت)" in keraa_text
print("  => PASS: Found 'أربعمائة وخمسون دينار (450 د.ت)' in Rent Contract!")

# Receipt Contract
wassl_text = build_multi_party_contract_text(
    contract_type="وصل خلاص",
    party1_list=party1,
    party2_list=party2,
    property_desc="عقد بيع سابق",
    price_num="3000",
    price_words=""
)
print("\nRECEIPT CONTRACT PRICE CLAUSE:")
print(wassl_text)
assert "ثلاثة آلاف دينار (3000 د.ت)" in wassl_text
print("  => PASS: Found 'ثلاثة آلاف دينار (3000 د.ت)' in Receipt Contract!")

print("\nALL TESTS PASSED PERFECTLY!")
