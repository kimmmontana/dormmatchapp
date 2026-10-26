from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    list_display =[ 'username','first_name', 'last_name', 'suffix', 'birthday', 'gender',
                    'contact_number', 'email', 'degree_program','is_staff','school' ]
    
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('suffix', 'birthday',
                            'gender', 'contact_number', 'degree_program', 'school')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':('username','first_name', 'last_name', 'suffix', 'birthday', 'gender', 
                      'contact_number', 'email', 'degree_program', 'school', 'password1', 'password2'),
        }),
    )

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.unregister(Group)