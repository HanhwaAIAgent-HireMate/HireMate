package com.hiremate.company;

import com.hiremate.company.domain.Company;
import com.hiremate.company.domain.CompanyRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CompanyService {

    private final CompanyRepository companies;

    public CompanyService(CompanyRepository companies) {
        this.companies = companies;
    }

    @Transactional
    public CompanyInfo createCompany(String name) {
        Company company = companies.save(new Company(name));
        return new CompanyInfo(company.getId(), company.getName());
    }
}
