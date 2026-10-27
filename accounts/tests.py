from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class CustomUserModelTests(TestCase):
    def test_age_is_computed_from_birthday(self):
        user = get_user_model()(username="kim", birthday=date(2000, 1, 1))
        today = date.today()
        expected = today.year - 2000 - ((today.month, today.day) < (1, 1))
        self.assertEqual(user.age, expected)

    def test_age_is_none_without_birthday(self):
        user = get_user_model()(username="kim")
        self.assertIsNone(user.age)


class SignUpViewTests(TestCase):
    def test_signup_page_renders(self):
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/signup.html")

    def test_signup_creates_user_and_redirects_to_login(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "student1",
                "first_name": "Juan",
                "last_name": "Dela Cruz",
                "gender": "Cisgender Male",
                "contact_number": "09171234567",
                "email": "juan@example.com",
                "school": "University of the Philippines",
                "degree_program": "BS Computer Science",
                "password1": "a-Strong-pass-123",
                "password2": "a-Strong-pass-123",
            },
        )
        self.assertRedirects(response, reverse("login"))
        self.assertTrue(get_user_model().objects.filter(username="student1").exists())

    def test_signup_rejects_duplicate_email(self):
        get_user_model().objects.create_user(username="existing", email="juan@example.com", password="x")
        response = self.client.post(
            reverse("signup"),
            {
                "username": "student1",
                "email": "juan@example.com",
                "password1": "a-Strong-pass-123",
                "password2": "a-Strong-pass-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="student1").exists())
