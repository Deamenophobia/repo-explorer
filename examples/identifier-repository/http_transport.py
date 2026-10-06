class HTTPTransport:
    def response_status(self, response):
        return response.status_code

    def response_body(self, response):
        return response.content
