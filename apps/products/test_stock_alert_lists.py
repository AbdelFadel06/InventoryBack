"""Vues « stock bas » et « rupture » : mêmes champs que la liste produits (prix, image)."""
from apps.accounts.test_permissions_baseline import PermissionFixtures
from apps.stocks.models import Stock


class StockAlertListFieldsTests(PermissionFixtures):

    def test_out_of_stock_rows_have_price_and_image_fields(self):
        Stock.objects.filter(product=self.product).update(quantity=0)
        body = self.call(self.manager, 'get', '/api/products/out_of_stock/').json()
        row = next(p for p in body['products'] if p['id'] == self.product.id)
        self.assertEqual(float(row['selling_price']), 1000)
        self.assertIn('primary_image', row)
        self.assertEqual(row['stock_status'], 'out_of_stock')
        self.assertEqual(row['current_stock'], 0)

    def test_low_stock_rows_have_price(self):
        self.product.minimum_stock = 50
        self.product.save()
        body = self.call(self.manager, 'get', '/api/products/low_stock/').json()
        row = next(p for p in body['products'] if p['id'] == self.product.id)
        self.assertEqual(float(row['selling_price']), 1000)
        self.assertIn('barcode', row)
