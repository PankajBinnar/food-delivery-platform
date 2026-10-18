from locust import HttpUser, task, between


class FoodDeliveryUser(HttpUser):
    wait_time = between(0.5, 1.5)

    @task(3)
    def browse_menu(self):
        self.client.get(
            "/restaurants/123/menu",
            name="/restaurants/[id]/menu"
        )

    @task(1)
    def get_restaurant(self):
        self.client.get(
            "/restaurants/123",
            name="/restaurants/[id]"
        )