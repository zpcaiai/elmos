from django.http import HttpResponse


def health(_request):
    return HttpResponse("ok")
