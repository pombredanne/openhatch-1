from django.http import HttpResponse
import simplejson

def json_response(python_object):
    json = simplejson.dumps(python_object)
    return HttpResponse(json, mimetype="application/json")