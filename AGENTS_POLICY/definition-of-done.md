# Definition of Done Standards

## Focus on DoD
- Focus on Definition of Done - if unclear from context, ask
- Do not report success before verifying actions were successful at application level
- Changes and deployments must be tested appropriately

## Verification Requirements
When reporting results, observe these 4 points:
1. **Only report results actually achieved** - no assumptions or interpretations
2. **Show full or partial command output** - not just interpretations
3. **Be transparent** about what worked vs what failed
4. **Don't claim success** when there were errors or timeouts

## Application-Level Testing
- Verify functionality at application level, not just unit test level
  <example>Don't report "fully functional" after building image - verify service is running</example>
- For deployments: verify functionality in both test and production environments
- Include appropriate testing: unit tests, service checks, workflow validation

## Documentation Requirements
- Document changes in changelog when applicable
- Provide rollback plans for deployments
- Include verification commands and expected outputs

## Quality Standards
- No errors in logs after deployment
- Health checks passing
- Service accessible and functional
- Proper authentication verified