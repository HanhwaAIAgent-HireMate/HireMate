package com.hiremate.global.error;

import com.hiremate.global.ApiException;
import com.hiremate.global.ProblemResponses;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ApiException.class)
    ProblemDetail handleApiException(ApiException exception) {
        return ProblemResponses.problem(exception.status(), exception.code(), exception.getMessage());
    }

    @ExceptionHandler({MethodArgumentNotValidException.class, HttpMessageNotReadableException.class})
    ProblemDetail handleInvalidInput(Exception exception) {
        return ProblemResponses.problem(HttpStatus.BAD_REQUEST, "INVALID_INPUT", "Check the request values.");
    }
}
