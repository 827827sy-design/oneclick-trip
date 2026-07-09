package com.oneclicktrip;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@MapperScan("com.oneclicktrip.mapper")
public class OneclickTripApplication {
    public static void main(String[] args) {
        SpringApplication.run(OneclickTripApplication.class, args);
    }
}

