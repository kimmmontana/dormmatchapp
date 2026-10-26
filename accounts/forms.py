from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import CustomUser

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm):
        model = CustomUser
        fields = ('username', 'first_name', 'last_name', 'suffix', 'birthday', 'gender', 
                  'contact_number', 'email', 'school','degree_program')

class CustomUserChangeForm(UserChangeForm):
    class Meta :
        model = CustomUser
        fields = ('username', 'first_name', 'last_name', 'suffix', 'birthday', 'gender', 
                  'contact_number', 'email','school', 'degree_program')
