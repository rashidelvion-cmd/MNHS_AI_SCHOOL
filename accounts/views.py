from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout


def user_login(request):

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect("dashboard")

        else:
            return render(
                request,
                "accounts/login.html",
                {
                    "error": "Invalid Username or Password"
                }
            )

    return render(request, "accounts/login.html")


def user_logout(request):

    logout(request)

    return redirect("login")