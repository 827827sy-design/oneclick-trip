package com.oneclicktrip.common;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {
    /**
     * 业务异常：例如用户名密码错误、城市不存在。
     * 这类错误不是程序崩了，而是用户请求本身不满足业务规则。
     */
    @ExceptionHandler(BusinessException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiResponse<Void> handleBusiness(BusinessException ex) {
        return ApiResponse.fail(ex.getMessage());
    }

    @ExceptionHandler(AiServiceException.class)
    @ResponseStatus(HttpStatus.BAD_GATEWAY)
    public ApiResponse<Void> handleAiService(AiServiceException ex) {
        return ApiResponse.fail(ex.getMessage());
    }

    /**
     * 参数校验异常：DTO 上的 @NotBlank、@Size 等校验失败时会走这里。
     */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiResponse<Void> handleValidation(MethodArgumentNotValidException ex) {
        String message = ex.getBindingResult().getFieldErrors().stream()
                .findFirst()
                .map(error -> error.getField() + " " + error.getDefaultMessage())
                .orElse("参数校验失败");
        return ApiResponse.fail(message);
    }

    @ExceptionHandler(AccessDeniedException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    public ApiResponse<Void> handleAccessDenied() {
        return ApiResponse.fail("没有访问权限");
    }

    /**
     * 兜底异常：开发阶段把真实错误信息返回出来，方便定位问题。
     * 正式上线时建议改成更通用的提示，并把详细错误写入日志。
     */
    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public ApiResponse<Void> handleUnexpected(Exception ex) {
        return ApiResponse.fail("系统异常：" + ex.getMessage());
    }
}
