import urllib.request
import io
import ssl


context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE
with urllib.request.urlopen('https://blog.csdn.net/nings666/article/details/1353710', context=context) as req:
    pdf_data = req.read()
print